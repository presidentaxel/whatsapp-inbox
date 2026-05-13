# Test Rapide avec Ngrok

## Étapes Rapides

### 1. Installer ngrok (si pas déjà fait)

**Ubuntu / Linux (bash)** — paquet ou archive depuis [ngrok.com/download](https://ngrok.com/download) :

```bash
# Ubuntu : souvent disponible via snap
sudo snap install ngrok
# Sinon : archive depuis https://ngrok.com/download
```

**Windows (PowerShell)** — avec Chocolatey :

```powershell
choco install ngrok
```

Sinon : télécharger depuis [ngrok.com/download](https://ngrok.com/download).

### 2. Démarrer le backend

**Ubuntu / Linux (bash)**

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

**Windows (PowerShell)**

```powershell
cd backend
uvicorn app.main:app --reload --port 8000
```

### 3. Lancer le script de test

**Ubuntu / Linux (bash)**

```bash
cd backend
python scripts/test_webhook_ngrok.py
```

**Windows (PowerShell)**

```powershell
cd backend
python scripts/test_webhook_ngrok.py
```

Le script va :
- ✅ Vérifier que ngrok est installé
- ✅ Vérifier que le backend est démarré
- ✅ Démarrer un tunnel ngrok
- ✅ Afficher l'URL publique ngrok
- ✅ Tester l'endpoint webhook
- ✅ Donner les instructions pour configurer Meta

### 4. Configurer Meta

1. Copiez l'URL ngrok affichée (ex: `https://xxxxx.ngrok.io/webhook/whatsapp`)
2. Allez dans Meta for Developers > Votre App > Webhooks > WhatsApp
3. Collez l'URL dans "URL de rappel"
4. Entrez le verify token (celui de votre .env)
5. Cliquez sur "Vérifier et enregistrer"
6. Vérifiez que "messages" est abonné
7. Testez avec le bouton "Test" ou "Envoyer au serveur v24.0"

### 5. Vérifier les Logs

Regardez les logs du backend. Vous devriez voir :
```
INFO:     📥 POST /webhook/whatsapp received from <IP>
INFO:     📥 POST /whatsapp webhook received: object=whatsapp_business_account, entries=1
...
```

## Alternative Manuelle

Si vous préférez faire manuellement :

### 1. Démarrer ngrok

```bash
ngrok http 8000
```

(Même commande dans PowerShell si `ngrok` est dans le `PATH`.)

### 2. Récupérer l'URL
- Ouvrez http://127.0.0.1:4040 dans votre navigateur
- Copiez l'URL "Forwarding" (ex: `https://xxxxx.ngrok.io`)

### 3. Configurer Meta
- URL de rappel: `https://xxxxx.ngrok.io/webhook/whatsapp`
- Verify token: (celui de votre .env)

### 4. Tester
- Utilisez le bouton "Test" dans Meta
- Regardez les logs du backend

## Notes Importantes

⚠️ **L'URL ngrok change à chaque redémarrage** (sauf avec un compte payant)

⚠️ **Ngrok doit rester actif** pendant les tests

✅ Si les webhooks arrivent via ngrok mais pas via l'URL de production, c'est un problème d'accessibilité de l'URL de production (firewall, DNS, etc.)

