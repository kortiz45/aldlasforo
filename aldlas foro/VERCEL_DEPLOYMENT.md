# Guía de Despliegue en Vercel

## Cambios Realizados para Compatibilidad con Vercel

Vercel es un entorno **serverless** con restricciones de escritura de archivos. Se han realizado los siguientes cambios para que tu proyecto funcione correctamente:

### 1. **Almacenamiento Temporal Movido a `/tmp/`**
- **Antes**: Los archivos temporales se guardaban en `/assets/uploads/_tmp/` (lectura/escritura prohibida en Vercel)
- **Ahora**: Se guardan en `/tmp/uploads/` (directorio disponible y escribible en Vercel)
- **Archivo modificado**: `backend/main.py` (línea 51)

### 2. **Creación de Directorios Protegida**
- Se envolvieron todas las llamadas `mkdir()` en bloques `try-except`
- Si un directorio no puede crearse (como `/assets/` en Vercel), no causará un error fatal
- **Archivo modificado**: `backend/main.py` (líneas 68-75)

### 3. **Manejo de Almacenamiento Local Mejorado**
- La función `move_to_local_storage()` ahora maneja errores de permisos elegantemente
- Si el almacenamiento local no está disponible, intenta usar `MEDIA_PUBLIC_BASE_URL`
- **Archivo modificado**: `backend/main.py` (líneas 1410-1437)

---

## Variables de Entorno Requeridas

Para desplegar en Vercel, configura estas variables en **Settings → Environment Variables**:

### Opción 1: Usar Supabase (Recomendado)
```
MEDIA_STORAGE_MODE=supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key
SUPABASE_BUCKET=foro-media
```

### Opción 2: Usar HostGator (URL Externa Manual)
```
MEDIA_PUBLIC_BASE_URL=https://tudominio.hostgator.com/assets
HOSTGATOR_BASE_URL=https://tudominio.hostgator.com/assets
```

⚠️ **Nota Importante**: Con HostGator, deberás subir manualmente los archivos usando FTP o configurar una integración personalizada. El código solo devolverá las URLs, no las subidas automáticas.

### Variables Adicionales
```
DATABASE_URL=postgresql://usuario:password@host:puerto/base_datos
ADMIN_API_KEY=tu_api_key_segura
ADMIN_USERNAME=admin
ADMIN_PASSWORD_SHA256=hash_sha256_de_tu_contraseña
FORCE_HTTPS=1
```

---

## Configuración del Archivo `vercel.json`

Tu archivo `vercel.json` ya está correctamente configurado:
```json
{
    "rewrites": [
        { "source": "/(.*)", "destination": "/api/index.py" }
    ]
}
```

---

## Flujo de Subida de Archivos en Vercel

### Versión Supabase (Automática)
1. Usuario sube archivo
2. Vercel guarda temporalmente en `/tmp/uploads/`
3. Se sube automáticamente a Supabase
4. Se obtiene URL pública de Supabase
5. Se limpia `/tmp/` después de la subida

### Versión HostGator (Manual)
1. Usuario sube archivo
2. Vercel guarda temporalmente en `/tmp/uploads/`
3. Se genera URL basada en `MEDIA_PUBLIC_BASE_URL`
4. **Requiere**: Subir manualmente a tu hosting HostGator

---

## Limitaciones en Vercel

❌ **NO disponible**:
- Creación de directorios en `/assets/` (read-only)
- Creación de directorios en `/data/` (read-only)
- Escritura de archivos locales permanentes

✅ **SÍ disponible**:
- `/tmp/` para almacenamiento temporal (límite: 512 MB)
- Variables de entorno
- PostgreSQL remoto (DATABASE_URL)
- Supabase Storage

---

## Recomendaciones

1. **Usa Supabase** cuando sea posible (más automático)
2. **Configura un PostgreSQL remoto** (Neon, Railway, Supabase)
3. **No guardes datos críticos en archivos locales**
4. **Usa variables de entorno** para todas las credenciales
5. **Monitorea el uso de `/tmp/`** en logs de Vercel

---

## Testing Local

Para probar localmente asegurate que `/tmp/uploads/` es escribible:
```bash
python -m backend.main
```

Si ves errores, verifica que tu workspace tiene permisos de escritura en `/tmp/`.

---

## Solución de Problemas

| Error | Causa | Solución |
|-------|-------|----------|
| `Read-only file system` | Intentan escribir en /assets/ | Configura SUPABASE_URL o MEDIA_PUBLIC_BASE_URL |
| `No SUPABASE_URL` | Variable de entorno no configurada | Añade en Vercel → Settings → Environment Variables |
| `/tmp/ full` | Muchos archivos temporales | Limpia manualmente o aumenta timeout |
| `PermissionError` en /data/ | Intentan escribir datos JSON localmente | Usa Database URL en lugar de JSON |

