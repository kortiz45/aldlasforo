# ✅ Checklist Pre-Deploy en Vercel

## Verificación Local

- [ ] **Verificación Python**
  ```bash
  cd D:\aldlas foro
  .\.venv\Scripts\python verify.py
  ```
  Resultado esperado: ✅ TODAS LAS VERIFICACIONES PASADAS

- [ ] **Test de inicio local**
  ```bash
  cd D:\aldlas foro
  run.bat
  ```
  Esperar a que diga: `Uvicorn running on http://0.0.0.0:8000`
  Luego presionar Ctrl+C para detener

- [ ] **Archivos críticos existen**
  - [ ] `aldlasforo/backend/main.py`
  - [ ] `aldlasforo/api/index.py`
  - [ ] `aldlasforo/vercel.json`
  - [ ] `aldlasforo/requirements.txt`

- [ ] **Estructura consolidada**
  - [ ] Existe solo `aldlasforo/` (sin espacios)
  - [ ] NO existe `aldlas foro/` (con espacios)
  - [ ] NO hay duplicados

---

## Antes de Desplegar en Vercel

- [ ] **Git commit de cambios**
  ```bash
  cd D:\aldlas foro
  git status  # Ver cambios
  git add .
  git commit -m "fix: Consolidar carpetas, hacer directorios opcionales"
  git push origin main
  ```

- [ ] **Environment Variables en Vercel**
  
  Configura en Vercel > Settings > Environment Variables:
  
  ```
  DATABASE_URL=postgresql://usuario:password@host/db
  SUPABASE_URL=https://tu-proyecto.supabase.co
  SUPABASE_SERVICE_ROLE_KEY=tu_service_role_key
  SUPABASE_BUCKET=foro-media
  MEDIA_STORAGE_MODE=supabase
  ADMIN_API_KEY=tu_api_key_segura
  ADMIN_USERNAME=admin
  ADMIN_PASSWORD_SHA256=hash_sha256
  FORCE_HTTPS=1
  CORS_ALLOW_ORIGINS=*
  ```

- [ ] **Vercel Deployment Settings**
  - [ ] Framework: `Other`
  - [ ] Root Directory: `aldlasforo/`
  - [ ] Build Command: (dejar vacío)
  - [ ] Output Directory: (dejar vacío)
  - [ ] Install Command: `pip install -r requirements.txt`
  - [ ] Start Command: (dejar vacío, Vercel lo maneja)

---

## Después del Deploy

- [ ] **Prueba en Vercel**
  - [ ] Abre `https://tu-dominio.vercel.app/`
  - [ ] Verifica que funciona (no 500)
  - [ ] Revisa los logs en Vercel por errores

- [ ] **Revisar Logs en Vercel**
  ```
  Vercel Dashboard > Deployments > [Tu Deployment] > Logs
  ```
  
  Busca errores como:
  - ❌ `No such file or directory: /assets/audio` → Debería ignorarse ahora
  - ❌ `favicon.ico not found` → Debería devolver 204
  - ❌ `permission denied` → Debería ignorarse

- [ ] **Prueba endpoints clave**
  - [ ] `GET /` → HTML del index
  - [ ] `GET /favicon.ico` → 204 No Content
  - [ ] `GET /assets/` → 404 o vacío (está OK)
  - [ ] `GET /api/` → Endpoints funcionan

---

## Troubleshooting

### Si aún obtienes Error 500...

1. **Verifica los logs:**
   ```
   Vercel Dashboard > Logs > Cloud Function Runtime
   ```

2. **Busca estos problemas comunes:**
   - ❌ `ModuleNotFoundError`: Algún import falta
     → Revisa `requirements.txt`
   
   - ❌ `Permission denied`: Vercel es read-only
     → Ya está solucionado en el código
   
   - ❌ `Connection refused DATABASE_URL`:
     → Verifica que DATABASE_URL sea correcto
   
   - ❌ `CORS error`: Client no puede conectar
     → Actualiza `CORS_ALLOW_ORIGINS`

3. **Redeploy:**
   ```bash
   git push origin main  # Vercel desplegará automáticamente
   ```

---

## 🎯 QUÉ NO DEBERÍA PASAR MÁS

❌ **Estos errores están SOLUCIONADOS:**
- "No such file or directory: /assets/audio" → ✅ Ahora ignorado
- "favicon.ico not found - 500 error" → ✅ Ahora 204 No Content
- "Permission denied creating directory" → ✅ Ahora envuelto en try-except
- Dos carpetas `aldlasforo` → ✅ Consolidadas en 1
- .venv con rutas viejas → ✅ Regenerado

---

## 📞 Si Todo Funciona

¡FELICIDADES! 🎉

Tu aplicación:
- ✅ Está consolidada sin duplicados
- ✅ Maneja directorios opcionales
- ✅ Favicon es opcional
- ✅ Compatible con Vercel serverless
- ✅ NO genera errores 500 por archivos faltantes

---

## 📝 Notas Importantes

- **Espacio en nombre:** `aldlas foro` → `aldlasforo` ✅
- **Directorios opcionales:** audio, recursos, videos ✅
- **Favicon:** 204 No Content ✅
- **Entorno virtual:** Regenerado ✅
- **Verificación:** Script `verify.py` ✅

---

**Estado**: ✅ LISTO PARA VERCEL

**Última confirmación**: 5 de Marzo de 2026 a las 21:35
