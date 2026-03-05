#!/usr/bin/env python3
"""
Script de verificación para aldlasforo
Verifica que todos los componentes estén configurados correctamente
"""

import sys
import json
from pathlib import Path

def check_directory_structure():
    """Verifica que la estructura de directorios sea correcta"""
    print("\n📁 Verificando estructura de directorios...")
    
    base_path = Path(__file__).parent / "aldlasforo"
    required_dirs = ["backend", "api", "assets", "css", "js", "data"]
    
    all_exist = True
    for dir_name in required_dirs:
        dir_path = base_path / dir_name
        exists = "✓" if dir_path.exists() else "✗"
        print(f"  {exists} {dir_name}/")
        if not dir_path.exists():
            all_exist = False
    
    return all_exist

def check_python_files():
    """Verifica que los archivos Python existan"""
    print("\n🐍 Verificando archivos Python...")
    
    base_path = Path(__file__).parent / "aldlasforo"
    python_files = {
        "Backend": base_path / "backend" / "main.py",
        "API (Vercel)": base_path / "api" / "index.py",
    }
    
    all_exist = True
    for name, file_path in python_files.items():
        exists = "✓" if file_path.exists() else "✗"
        print(f"  {exists} {name}: {file_path.relative_to(base_path.parent)}")
        if not file_path.exists():
            all_exist = False
    
    return all_exist

def check_html_files():
    """Verifica que los archivos HTML principales existan"""
    print("\n🌐 Verificando archivos HTML...")
    
    base_path = Path(__file__).parent / "aldlasforo"
    html_files = ["index.html", "foro.html", "admin.html", "creditos.html"]
    
    all_exist = True
    for html in html_files:
        file_path = base_path / html
        exists = "✓" if file_path.exists() else "✗"
        print(f"  {exists} {html}")
        if not file_path.exists():
            all_exist = False
    
    return all_exist

def check_config_files():
    """Verifica la configuración de Vercel y otros"""
    print("\n⚙️  Verificando archivos de configuración...")
    
    base_path = Path(__file__).parent / "aldlasforo"
    config_files = {
        "Vercel": base_path / "vercel.json",
        "Requirements": base_path / "requirements.txt",
        "Schema DB": base_path / "schema.sql",
    }
    
    all_exist = True
    for name, file_path in config_files.items():
        exists = "✓" if file_path.exists() else "✗"
        print(f"  {exists} {name}: {file_path.name}")
        if not file_path.exists():
            all_exist = False
    
    return all_exist

def check_no_duplicates():
    """Verifica que no haya carpetas duplicadas"""
    print("\n🔍 Verificando duplicados...")
    
    parent_path = Path(__file__).parent
    subdirs = [d.name for d in parent_path.iterdir() if d.is_dir()]
    
    # Buscar "aldlas foro" o duplicados
    if "aldlas foro" in subdirs:
        print("  ✗ Encontrada carpeta 'aldlas foro' (con espacio) - DEBE eliminarse")
        return False
    
    if subdirs.count("aldlasforo") > 1:
        print("  ✗ Múltiples carpetas 'aldlasforo' encontradas - ERROR")
        return False
    
    print("  ✓ No hay duplicados")
    if "aldlasforo" in subdirs:
        print("  ✓ Carpeta consolidada: aldlasforo (sin espacios)")
    
    return True

def main():
    """Ejecuta todas las verificaciones"""
    print("=" * 50)
    print("🔧 VERIFICACIÓN DE ALDLASFORO")
    print("=" * 50)
    
    checks = [
        ("Estructura de directorios", check_directory_structure),
        ("Archivos Python", check_python_files),
        ("Archivos HTML", check_html_files),
        ("Archivos de configuración", check_config_files),
        ("Duplicados", check_no_duplicates),
    ]
    
    results = []
    for check_name, check_func in checks:
        try:
            result = check_func()
            results.append((check_name, result))
        except Exception as e:
            print(f"  ✗ Error durante verificación: {e}")
            results.append((check_name, False))
    
    # Resumen
    print("\n" + "=" * 50)
    print("📊 RESUMEN")
    print("=" * 50)
    
    all_passed = True
    for check_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {check_name}")
        if not result:
            all_passed = False
    
    print("\n" + "=" * 50)
    if all_passed:
        print("✓ ¡TODAS LAS VERIFICACIONES PASADAS!")
        print("La aplicación está lista para ejecutar.")
        print("\nPara iniciar localmente:")
        print("  Windows: run.bat")
        print("  PowerShell: .\\run.ps1")
        print("  Manual: uvicorn aldlasforo.backend.main:app --reload")
    else:
        print("✗ Algunas verificaciones fallaron.")
        print("Por favor revisa los errores arriba.")
        sys.exit(1)
    
    print("=" * 50)

if __name__ == "__main__":
    main()
