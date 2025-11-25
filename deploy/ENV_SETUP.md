# Configuration des variables d'environnement pour la production

## Fichier `.env` requis

Pour que Caddy et Grafana fonctionnent correctement, vous devez créer un fichier `.env` dans le dossier `deploy/` avec les variables suivantes :

```bash
# Domaine de votre application (sans https://)
DOMAIN=whatsapp.lamaisonduchauffeurvtc.fr

# Email pour les certificats SSL Let's Encrypt (Caddy)
# Cet email sera utilisé pour les notifications Let's Encrypt
EMAIL=votre-email@example.com
```

## Instructions

1. Créez le fichier `deploy/.env` :
   ```bash
   cd deploy
   cat > .env << EOF
   DOMAIN=whatsapp.lamaisonduchauffeurvtc.fr
   EMAIL=votre-email@example.com
   EOF
   ```

2. Remplacez les valeurs :
   - `DOMAIN` : Votre domaine (d'après votre config, c'est `whatsapp.lamaisonduchauffeurvtc.fr`)
   - `EMAIL` : Votre adresse email (pour les certificats SSL)

3. Redémarrez les services :
   ```bash
   docker-compose -f docker-compose.prod.yml down
   docker-compose -f docker-compose.prod.yml up -d
   ```

## Vérification

Après avoir créé le fichier `.env` et redémarré, vérifiez que :
- Caddy démarre sans erreur : `docker-compose -f docker-compose.prod.yml logs caddy`
- Grafana est accessible : `https://votre-domaine.com/grafana`
- Les certificats SSL sont générés automatiquement par Let's Encrypt

## Sécurité

⚠️ **Important** : Ne commitez jamais le fichier `.env` dans Git. Il contient des informations sensibles.

