#!/bin/bash
# Script para ejecutar Scrapelillo con el entorno virtual activado

# Activar entorno virtual
source venv/bin/activate

# Ejecutar scrapelillo
python3 scrap.py

# Desactivar al salir
deactivate
