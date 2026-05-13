/**
 * Script pour générer les icônes PWA à partir du favicon.svg
 * 
 * Utilisation:
 * 1. Installer les dépendances: npm install --save-dev sharp
 * 2. Exécuter: node scripts/generate-pwa-icons.js
 * 
 * Alternative simple:
 * - Utilisez un service en ligne comme https://realfavicongenerator.net/
 * - Ou https://favicon.io/favicon-converter/
 * - Uploadez le favicon.svg et téléchargez les icônes générées
 */

const fs = require('fs');
const path = require('path');

async function generateIcons() {
  try {
    // Vérifier si sharp est installé
    const sharp = require('sharp');
    
    const svgPath = path.join(__dirname, '../public/favicon.svg');
    const publicPath = path.join(__dirname, '../public');
    
    // Lire le SVG
    const svgBuffer = fs.readFileSync(svgPath);
    
    // Générer les différentes tailles
    const sizes = [192, 512];
    
    for (const size of sizes) {
      await sharp(svgBuffer)
        .resize(size, size)
        .png()
        .toFile(path.join(publicPath, `icon-${size}x${size}.png`));
      
      console.log(`✅ Icône ${size}x${size} générée`);
    }
    
    console.log('\n🎉 Toutes les icônes PWA ont été générées avec succès!');
    
  } catch (error) {
    if (error.code === 'MODULE_NOT_FOUND') {
      console.error('\n❌ Module "sharp" non trouvé.');
      console.log('\n📋 Solutions alternatives:');
      console.log('   1. Installer sharp: npm install --save-dev sharp');
      console.log('   2. OU utiliser un service en ligne:');
      console.log('      • https://realfavicongenerator.net/');
      console.log('      • https://favicon.io/favicon-converter/');
      console.log('   3. OU créer manuellement des PNG 192x192 et 512x512');
      console.log('\n💡 Les icônes doivent être placées dans frontend/public/');
    } else {
      console.error('❌ Erreur lors de la génération des icônes:', error);
    }
    process.exit(1);
  }
}

// Si le module est exécuté directement
if (require.main === module) {
  generateIcons();
}

module.exports = { generateIcons };

