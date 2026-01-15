# MIME Type Fix for .mjs Files

## Problem

The application was experiencing errors when loading JavaScript module files (`.mjs`), specifically `pdf.worker.min.mjs`:

```
Failed to load module script: The server responded with a non-JavaScript MIME type of "application/octet-stream". 
Strict MIME type checking is enforced for module scripts per HTML spec.
```

## Root Cause

The web server (Caddy + Nginx) was serving `.mjs` files with the wrong MIME type (`application/octet-stream` instead of `application/javascript`). This happens because:

1. Browsers require ES modules (`.mjs` files) to be served with the correct JavaScript MIME type
2. Some web servers don't recognize `.mjs` as JavaScript by default
3. When Caddy proxies to Nginx, headers need to be configured at both levels

## Solution

### 1. Caddy Configuration (`deploy/Caddyfile` and `deploy/Caddyfile.prod`)

Added a specific handler for `.mjs` files that sets the correct Content-Type header before proxying to the frontend:

```caddy
# Configure MIME types for JavaScript modules before proxying
# Critical: .mjs files must be served with application/javascript MIME type
@mjs path *.mjs
handle @mjs {
  header Content-Type application/javascript
  reverse_proxy frontend:80
}
```

This ensures that when Caddy receives a request for a `.mjs` file, it sets the correct MIME type header before proxying to Nginx.

### 2. Nginx Configuration (`frontend/nginx.conf`)

Enhanced the existing `.mjs` location block to force the Content-Type header:

```nginx
location ~* \.mjs$ {
    default_type application/javascript;
    add_header Content-Type application/javascript always;
    expires 1y;
    add_header Cache-Control "public, immutable";
    try_files $uri =404;
}
```

The `always` parameter ensures the header is set even if it was already present, providing a fallback if Caddy doesn't set it.

## Files Modified

1. `deploy/Caddyfile` - Added `.mjs` handler
2. `deploy/Caddyfile.prod` - Added `.mjs` handler  
3. `frontend/nginx.conf` - Enhanced `.mjs` location block with `always` flag

## Deployment

After making these changes:

1. **For Docker Compose deployments:**
   ```bash
   docker-compose -f deploy/docker-compose.prod.yml restart caddy frontend
   ```

2. **For manual deployments:**
   - Restart Caddy to reload the Caddyfile
   - Rebuild/restart the frontend container to apply nginx.conf changes

## Verification

After deployment, verify the fix by:

1. Opening browser DevTools → Network tab
2. Loading a page that uses PDF thumbnails
3. Checking that `pdf.worker.min.mjs` is loaded with `Content-Type: application/javascript`
4. Verifying no MIME type errors in the console

## Additional Notes

- The `pdf.worker.min.mjs` file is located in `frontend/public/` and is copied to the root of `dist/` during build
- The PDF worker is used by `PDFThumbnail.jsx` component for rendering PDF previews
- This fix ensures compatibility with strict MIME type checking in modern browsers

