"""
ETL Pipeline for Professional Web Scraper

Implements Extract, Transform, Load pipeline with data transformation,
validation, cleaning, and multiple output formats.
"""

import logging
import json
import csv
import sqlite3
from typing import Dict, List, Any, Optional, Union, Callable
from dataclasses import dataclass, field
from datetime import datetime
import threading
from pathlib import Path
import re
from collections import defaultdict
import hashlib
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)


@dataclass
class ETLStep:
    """Represents an ETL processing step"""
    name: str
    function: Callable
    enabled: bool = True
    description: str = ""
    config: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ETLResult:
    """Result of ETL processing"""
    input_count: int = 0
    output_count: int = 0
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    processing_time: float = 0.0
    step_results: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DataRecord:
    """Represents a data record in the ETL pipeline"""
    data: Dict[str, Any]
    source: str
    timestamp: datetime
    record_id: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    validation_errors: List[str] = field(default_factory=list)
    processing_status: str = "pending"


class ETLPipeline:
    """
    ETL Pipeline for processing scraped data
    """
    
    def __init__(self, config_manager=None):
        """
        Initialize ETL pipeline
        
        Args:
            config_manager: Configuration manager instance
        """
        from .config_manager import ConfigManager
        self.config = config_manager or ConfigManager()
        
        etl_config = self.config.get_section('etl')
        self.enabled = etl_config.get('enabled', True)
        
        if not self.enabled:
            logger.info("ETL pipeline disabled")
            return
        
        # Configuration
        self.max_workers = etl_config.get('max_workers', 4)
        self.batch_size = etl_config.get('batch_size', 100)
        self.enable_validation = etl_config.get('enable_validation', True)
        self.enable_cleaning = etl_config.get('enable_cleaning', True)
        self.enable_deduplication = etl_config.get('enable_deduplication', True)
        
        # Output configuration
        self.output_formats = etl_config.get('output_formats', ['json', 'csv'])
        self.output_directory = etl_config.get('output_directory', 'output')
        self.database_path = etl_config.get('database_path', 'etl_data.db')
        
        # Validation rules
        self.validation_rules = etl_config.get('validation_rules', {})
        
        # Cleaning rules
        self.cleaning_rules = etl_config.get('cleaning_rules', {})
        
        # Transformation rules
        self.transformation_rules = etl_config.get('transformation_rules', {})
        
        # Initialize ETL steps
        self.steps = self._initialize_steps()
        
        # Thread safety
        self._lock = threading.Lock()
        
        # Initialize output directory
        Path(self.output_directory).mkdir(exist_ok=True)
        
        # Initialize database
        self._init_database()
        
        logger.info("ETL pipeline initialized")
    
    def _initialize_steps(self) -> List[ETLStep]:
        """Initialize ETL processing steps"""
        steps = []
        
        # Extract step
        steps.append(ETLStep(
            name="extract",
            function=self._extract_data,
            enabled=True,
            description="Extract data from input sources"
        ))
        
        # Validate step
        if self.enable_validation:
            steps.append(ETLStep(
                name="validate",
                function=self._validate_data,
                enabled=True,
                description="Validate data against rules",
                config=self.validation_rules
            ))
        
        # Clean step
        if self.enable_cleaning:
            steps.append(ETLStep(
                name="clean",
                function=self._clean_data,
                enabled=True,
                description="Clean and normalize data",
                config=self.cleaning_rules
            ))
        
        # Transform step
        steps.append(ETLStep(
            name="transform",
            function=self._transform_data,
            enabled=True,
            description="Transform data according to rules",
            config=self.transformation_rules
        ))
        
        # Deduplicate step
        if self.enable_deduplication:
            steps.append(ETLStep(
                name="deduplicate",
                function=self._deduplicate_data,
                enabled=True,
                description="Remove duplicate records"
            ))
        
        # Load step
        steps.append(ETLStep(
            name="load",
            function=self._load_data,
            enabled=True,
            description="Load data to output destinations"
        ))
        
        return steps
    
    def _init_database(self):
        """Initialize SQLite database for ETL data"""
        try:
            conn = sqlite3.connect(self.database_path)
            cursor = conn.cursor()
            
            # Create tables
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS etl_records (
                    id TEXT PRIMARY KEY,
                    data TEXT NOT NULL,
                    source TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    metadata TEXT,
                    validation_errors TEXT,
                    processing_status TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS etl_processing_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    step_name TEXT NOT NULL,
                    input_count INTEGER NOT NULL,
                    output_count INTEGER NOT NULL,
                    errors TEXT,
                    warnings TEXT,
                    processing_time REAL NOT NULL,
                    timestamp TEXT NOT NULL
                )
            ''')
            
            # Create indexes
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_etl_records_source ON etl_records(source)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_etl_records_status ON etl_records(processing_status)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_etl_log_timestamp ON etl_processing_log(timestamp)')
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Failed to initialize ETL database: {e}")
    
    def process_data(self, input_data: List[Dict[str, Any]], source: str = "scraper") -> ETLResult:
        """
        Process data through the ETL pipeline
        
        Args:
            input_data: List of data dictionaries to process
            source: Source identifier for the data
            
        Returns:
            ETLResult with processing statistics
        """
        if not self.enabled:
            return ETLResult()
        
        import time
        start_time = time.time()
        
        result = ETLResult(input_count=len(input_data))
        current_data = input_data
        
        logger.info(f"Starting ETL processing for {len(input_data)} records from {source}")
        
        try:
            # Process through each step
            for step in self.steps:
                if not step.enabled:
                    continue
                
                step_start_time = time.time()
                logger.info(f"Processing step: {step.name}")
                
                try:
                    # Execute step
                    step_result = step.function(current_data, source, step.config)
                    
                    # Update current data
                    if isinstance(step_result, list):
                        current_data = step_result
                    elif isinstance(step_result, dict) and 'data' in step_result:
                        current_data = step_result['data']
                        if 'errors' in step_result:
                            result.errors.extend(step_result['errors'])
                        if 'warnings' in step_result:
                            result.warnings.extend(step_result['warnings'])
                    
                    # Record step result
                    step_time = time.time() - step_start_time
                    result.step_results[step.name] = {
                        'input_count': len(current_data),
                        'processing_time': step_time,
                        'description': step.description
                    }
                    
                    logger.info(f"Step {step.name} completed: {len(current_data)} records in {step_time:.2f}s")
                    
                except Exception as e:
                    error_msg = f"Error in step {step.name}: {e}"
                    logger.error(error_msg)
                    result.errors.append(error_msg)
                    break
            
            # Update final result
            result.output_count = len(current_data)
            result.processing_time = time.time() - start_time
            
            # Log processing
            self._log_processing(result, source)
            
            logger.info(f"ETL processing completed: {result.output_count} records in {result.processing_time:.2f}s")
            
        except Exception as e:
            error_msg = f"Error in ETL processing: {e}"
            logger.error(error_msg)
            result.errors.append(error_msg)
        
        return result
    
    def _extract_data(self, data: List[Dict[str, Any]], source: str, config: Dict[str, Any]) -> List[DataRecord]:
        """Extract data and convert to DataRecord objects"""
        records = []
        
        for item in data:
            try:
                # Generate record ID
                record_id = self._generate_record_id(item, source)
                
                # Create DataRecord
                record = DataRecord(
                    data=item,
                    source=source,
                    timestamp=datetime.now(),
                    record_id=record_id,
                    metadata={
                        'extraction_time': datetime.now().isoformat(),
                        'source_type': source
                    }
                )
                
                records.append(record)
                
            except Exception as e:
                logger.error(f"Error extracting record: {e}")
                continue
        
        return records
    
    def _validate_data(self, records: List[DataRecord], source: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """Validate data records against rules"""
        valid_records = []
        errors = []
        warnings = []
        
        for record in records:
            record_errors = []
            record_warnings = []
            
            # Apply validation rules
            for field, rules in config.items():
                if field in record.data:
                    value = record.data[field]
                    
                    # Required field validation
                    if rules.get('required', False) and not value:
                        record_errors.append(f"Field '{field}' is required")
                    
                    # Type validation
                    expected_type = rules.get('type')
                    if expected_type and value is not None:
                        if expected_type == 'string' and not isinstance(value, str):
                            record_errors.append(f"Field '{field}' must be string")
                        elif expected_type == 'number' and not isinstance(value, (int, float)):
                            record_errors.append(f"Field '{field}' must be number")
                        elif expected_type == 'boolean' and not isinstance(value, bool):
                            record_errors.append(f"Field '{field}' must be boolean")
                    
                    # Length validation
                    if isinstance(value, str):
                        min_length = rules.get('min_length')
                        max_length = rules.get('max_length')
                        
                        if min_length and len(value) < min_length:
                            record_errors.append(f"Field '{field}' must be at least {min_length} characters")
                        
                        if max_length and len(value) > max_length:
                            record_errors.append(f"Field '{field}' must be at most {max_length} characters")
                    
                    # Pattern validation
                    pattern = rules.get('pattern')
                    if pattern and isinstance(value, str):
                        if not re.search(pattern, value):
                            record_errors.append(f"Field '{field}' does not match pattern")
                    
                    # Custom validation
                    custom_validator = rules.get('validator')
                    if custom_validator and callable(custom_validator):
                        try:
                            if not custom_validator(value):
                                record_errors.append(f"Field '{field}' failed custom validation")
                        except Exception as e:
                            record_errors.append(f"Field '{field}' validation error: {e}")
            
            # Update record with validation results
            record.validation_errors = record_errors
            record.processing_status = "valid" if not record_errors else "invalid"
            
            if record_errors:
                errors.extend([f"{record.record_id}: {error}" for error in record_errors])
            else:
                valid_records.append(record)
            
            if record_warnings:
                warnings.extend([f"{record.record_id}: {warning}" for warning in record_warnings])
        
        return {
            'data': valid_records,
            'errors': errors,
            'warnings': warnings
        }
    
    def _clean_data(self, records: List[DataRecord], source: str, config: Dict[str, Any]) -> List[DataRecord]:
        """Clean and normalize data records"""
        cleaned_records = []
        
        for record in records:
            try:
                cleaned_data = record.data.copy()
                
                # Apply cleaning rules
                for field, rules in config.items():
                    if field in cleaned_data:
                        value = cleaned_data[field]
                        
                        # String cleaning
                        if isinstance(value, str):
                            # Trim whitespace
                            if rules.get('trim', True):
                                value = value.strip()
                            
                            # Remove extra whitespace
                            if rules.get('normalize_whitespace', True):
                                value = re.sub(r'\s+', ' ', value)
                            
                            # Convert case
                            case = rules.get('case')
                            if case == 'lower':
                                value = value.lower()
                            elif case == 'upper':
                                value = value.upper()
                            elif case == 'title':
                                value = value.title()
                            
                            # Remove special characters
                            if rules.get('remove_special_chars', False):
                                value = re.sub(r'[^\w\s]', '', value)
                            
                            # Replace patterns
                            replacements = rules.get('replacements', {})
                            for pattern, replacement in replacements.items():
                                value = re.sub(pattern, replacement, value)
                        
                        # Number cleaning
                        elif isinstance(value, (int, float)):
                            # Round numbers
                            precision = rules.get('precision')
                            if precision is not None:
                                value = round(value, precision)
                            
                            # Clamp values
                            min_value = rules.get('min_value')
                            max_value = rules.get('max_value')
                            
                            if min_value is not None and value < min_value:
                                value = min_value
                            if max_value is not None and value > max_value:
                                value = max_value
                        
                        cleaned_data[field] = value
                
                # Update record
                record.data = cleaned_data
                cleaned_records.append(record)
                
            except Exception as e:
                logger.error(f"Error cleaning record {record.record_id}: {e}")
                cleaned_records.append(record)
        
        return cleaned_records
    
    def _transform_data(self, records: List[DataRecord], source: str, config: Dict[str, Any]) -> List[DataRecord]:
        """Transform data records according to rules"""
        transformed_records = []
        
        for record in records:
            try:
                transformed_data = record.data.copy()
                
                # Apply transformation rules
                for field, rules in config.items():
                    if field in transformed_data:
                        value = transformed_data[field]
                        
                        # Field mapping
                        if 'map_to' in rules:
                            new_field = rules['map_to']
                            transformed_data[new_field] = value
                            if rules.get('remove_original', False):
                                del transformed_data[field]
                        
                        # Value transformation
                        if 'transform' in rules:
                            transform_func = rules['transform']
                            if callable(transform_func):
                                try:
                                    transformed_data[field] = transform_func(value)
                                except Exception as e:
                                    logger.warning(f"Transform function failed for field {field}: {e}")
                        
                        # Concatenation
                        if 'concatenate' in rules:
                            concat_fields = rules['concatenate']
                            separator = rules.get('separator', ' ')
                            concat_values = []
                            
                            for concat_field in concat_fields:
                                if concat_field in transformed_data:
                                    concat_values.append(str(transformed_data[concat_field]))
                            
                            if concat_values:
                                transformed_data[field] = separator.join(concat_values)
                        
                        # Splitting
                        if 'split' in rules:
                            if isinstance(value, str):
                                delimiter = rules.get('delimiter', ' ')
                                parts = value.split(delimiter)
                                
                                if 'output_fields' in rules:
                                    output_fields = rules['output_fields']
                                    for i, output_field in enumerate(output_fields):
                                        if i < len(parts):
                                            transformed_data[output_field] = parts[i]
                
                # Update record
                record.data = transformed_data
                transformed_records.append(record)
                
            except Exception as e:
                logger.error(f"Error transforming record {record.record_id}: {e}")
                transformed_records.append(record)
        
        return transformed_records
    
    def _deduplicate_data(self, records: List[DataRecord], source: str, config: Dict[str, Any]) -> List[DataRecord]:
        """Remove duplicate records"""
        seen_records = set()
        unique_records = []
        
        for record in records:
            # Create hash of record data for comparison
            record_hash = self._generate_record_hash(record.data)
            
            if record_hash not in seen_records:
                seen_records.add(record_hash)
                unique_records.append(record)
            else:
                logger.debug(f"Removing duplicate record: {record.record_id}")
        
        logger.info(f"Deduplication: {len(records)} -> {len(unique_records)} records")
        return unique_records
    
    def _load_data(self, records: List[DataRecord], source: str, config: Dict[str, Any]) -> List[DataRecord]:
        """Load data to output destinations"""
        try:
            # Store in database
            self._store_records_database(records)
            
            # Export to files
            for format_type in self.output_formats:
                self._export_records(records, source, format_type)
            
            # Update processing status
            for record in records:
                record.processing_status = "loaded"
            
        except Exception as e:
            logger.error(f"Error loading data: {e}")
            for record in records:
                record.processing_status = "load_error"
        
        return records
    
    def _store_records_database(self, records: List[DataRecord]):
        """Store records in SQLite database"""
        try:
            conn = sqlite3.connect(self.database_path)
            cursor = conn.cursor()
            
            for record in records:
                cursor.execute('''
                    INSERT OR REPLACE INTO etl_records 
                    (id, data, source, timestamp, metadata, validation_errors, processing_status, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    record.record_id,
                    json.dumps(record.data),
                    record.source,
                    record.timestamp.isoformat(),
                    json.dumps(record.metadata),
                    json.dumps(record.validation_errors),
                    record.processing_status,
                    datetime.now().isoformat()
                ))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Error storing records in database: {e}")
    
    def _export_records(self, records: List[DataRecord], source: str, format_type: str):
        """Export records to file"""
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"{source}_{timestamp}.{format_type}"
            filepath = Path(self.output_directory) / filename
            
            if format_type.lower() == 'json':
                self._export_json(records, filepath)
            elif format_type.lower() == 'csv':
                self._export_csv(records, filepath)
            elif format_type.lower() == 'xlsx':
                self._export_xlsx(records, filepath)
            else:
                logger.warning(f"Unsupported export format: {format_type}")
                
        except Exception as e:
            logger.error(f"Error exporting records to {format_type}: {e}")
    
    def _export_json(self, records: List[DataRecord], filepath: Path):
        """Export records as JSON"""
        data = []
        for record in records:
            export_record = {
                'record_id': record.record_id,
                'source': record.source,
                'timestamp': record.timestamp.isoformat(),
                'data': record.data,
                'metadata': record.metadata,
                'validation_errors': record.validation_errors,
                'processing_status': record.processing_status
            }
            data.append(export_record)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Exported {len(records)} records to {filepath}")
    
    def _export_csv(self, records: List[DataRecord], filepath: Path):
        """Export records as CSV"""
        if not records:
            return
        
        # Get all unique fields
        all_fields = set()
        for record in records:
            all_fields.update(record.data.keys())
        
        fieldnames = ['record_id', 'source', 'timestamp', 'processing_status'] + sorted(all_fields)
        
        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            
            for record in records:
                row = {
                    'record_id': record.record_id,
                    'source': record.source,
                    'timestamp': record.timestamp.isoformat(),
                    'processing_status': record.processing_status
                }
                row.update(record.data)
                writer.writerow(row)
        
        logger.info(f"Exported {len(records)} records to {filepath}")
    
    def _export_xlsx(self, records: List[DataRecord], filepath: Path):
        """Export records as Excel"""
        if not records:
            return
        
        # Convert to DataFrame
        data = []
        for record in records:
            row = {
                'record_id': record.record_id,
                'source': record.source,
                'timestamp': record.timestamp.isoformat(),
                'processing_status': record.processing_status
            }
            row.update(record.data)
            data.append(row)
        
        df = pd.DataFrame(data)
        df.to_excel(filepath, index=False)
        
        logger.info(f"Exported {len(records)} records to {filepath}")
    
    def _generate_record_id(self, data: Dict[str, Any], source: str) -> str:
        """Generate unique record ID"""
        # Create hash from data and source
        content = json.dumps(data, sort_keys=True) + source
        return hashlib.md5(content.encode()).hexdigest()
    
    def _generate_record_hash(self, data: Dict[str, Any]) -> str:
        """Generate hash for deduplication"""
        # Create hash from data (excluding metadata fields)
        content = json.dumps(data, sort_keys=True)
        return hashlib.md5(content.encode()).hexdigest()
    
    def _log_processing(self, result: ETLResult, source: str):
        """Log processing results to database"""
        try:
            conn = sqlite3.connect(self.database_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO etl_processing_log 
                (step_name, input_count, output_count, errors, warnings, processing_time, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                'etl_pipeline',
                result.input_count,
                result.output_count,
                json.dumps(result.errors),
                json.dumps(result.warnings),
                result.processing_time,
                datetime.now().isoformat()
            ))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            logger.error(f"Error logging processing results: {e}")
    
    def get_processing_statistics(self) -> Dict[str, Any]:
        """Get ETL processing statistics"""
        try:
            conn = sqlite3.connect(self.database_path)
            cursor = conn.cursor()
            
            # Get total records
            cursor.execute('SELECT COUNT(*) FROM etl_records')
            total_records = cursor.fetchone()[0]
            
            # Get records by status
            cursor.execute('SELECT processing_status, COUNT(*) FROM etl_records GROUP BY processing_status')
            status_counts = dict(cursor.fetchall())
            
            # Get records by source
            cursor.execute('SELECT source, COUNT(*) FROM etl_records GROUP BY source')
            source_counts = dict(cursor.fetchall())
            
            # Get recent processing times
            cursor.execute('''
                SELECT AVG(processing_time), MAX(processing_time), MIN(processing_time)
                FROM etl_processing_log
                WHERE timestamp > datetime('now', '-7 days')
            ''')
            time_stats = cursor.fetchone()
            
            conn.close()
            
            return {
                'total_records': total_records,
                'status_counts': status_counts,
                'source_counts': source_counts,
                'avg_processing_time': time_stats[0] if time_stats[0] else 0,
                'max_processing_time': time_stats[1] if time_stats[1] else 0,
                'min_processing_time': time_stats[2] if time_stats[2] else 0
            }
            
        except Exception as e:
            logger.error(f"Error getting processing statistics: {e}")
            return {}
    
    def clear_database(self):
        """Clear all data from the ETL database"""
        try:
            conn = sqlite3.connect(self.database_path)
            cursor = conn.cursor()
            
            cursor.execute('DELETE FROM etl_records')
            cursor.execute('DELETE FROM etl_processing_log')
            
            conn.commit()
            conn.close()
            
            logger.info("ETL database cleared")
            
        except Exception as e:
            logger.error(f"Error clearing ETL database: {e}")
    
    def export_database(self, filepath: str, format: str = "json"):
        """Export all data from the ETL database"""
        try:
            conn = sqlite3.connect(self.database_path)
            cursor = conn.cursor()
            
            cursor.execute('SELECT * FROM etl_records')
            records = cursor.fetchall()
            
            conn.close()
            
            if format.lower() == "json":
                data = []
                for record in records:
                    data.append({
                        'id': record[0],
                        'data': json.loads(record[1]),
                        'source': record[2],
                        'timestamp': record[3],
                        'metadata': json.loads(record[4]) if record[4] else {},
                        'validation_errors': json.loads(record[5]) if record[5] else [],
                        'processing_status': record[6],
                        'created_at': record[7]
                    })
                
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Exported {len(records)} records from database to {filepath}")
            
        except Exception as e:
            logger.error(f"Error exporting database: {e}") 