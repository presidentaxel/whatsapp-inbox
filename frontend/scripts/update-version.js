#!/usr/bin/env node

/**
 * Script pour mettre à jour automatiquement la version dans tous les fichiers
 * Usage: node scripts/update-version.js <nouvelle_version>
 * Exemple: node scripts/update-version.js v2.0.2
 */

const fs = require('fs');
const path = require('path');

const NEW_VERSION = process.argv[2];

if (!NEW_VERSION) {
  console.error('❌ Erreur: Veuillez spécifier une version');
  console.log('Usage: node scripts/update-version.js <version>');
  console.log('Exemple: node scripts/update-version.js v2.0.2');
  process.exit(1);
}

// Vérifier le format de version (optionnel, mais recommandé)
if (!/^v?\d+\.\d+\.\d+/.test(NEW_VERSION)) {
  console.warn('⚠️  Attention: Le format de version ne suit pas le pattern vX.Y.Z');
}

const VERSION_WITHOUT_V = NEW_VERSION.startsWith('v') ? NEW_VERSION.substring(1) : NEW_VERSION;
const VERSION_WITH_V = NEW_VERSION.startsWith('v') ? NEW_VERSION : `v${NEW_VERSION}`;

console.log(`🔄 Mise à jour de la version vers ${VERSION_WITH_V}...`);

// 1. Mettre à jour sw.js
const swPath = path.join(__dirname, '../public/sw.js');
let swContent = fs.readFileSync(swPath, 'utf8');
swContent = swContent.replace(/const SW_VERSION = ['"]([^'"]+)['"];/, `const SW_VERSION = '${VERSION_WITH_V}';`);
fs.writeFileSync(swPath, swContent);
console.log('✅ sw.js mis à jour');

// 2. Mettre à jour manifest.json
const manifestPath = path.join(__dirname, '../public/manifest.json');
let manifestContent = fs.readFileSync(manifestPath, 'utf8');
// Remplacer toutes les occurrences de ?v=vX.X.X
manifestContent = manifestContent.replace(/\?v=v\d+\.\d+\.\d+/g, `?v=${VERSION_WITH_V}`);
fs.writeFileSync(manifestPath, manifestContent);
console.log('✅ manifest.json mis à jour');

// 3. Mettre à jour index.html
const indexPath = path.join(__dirname, '../index.html');
let indexContent = fs.readFileSync(indexPath, 'utf8');
// Remplacer toutes les occurrences de ?v=vX.X.X dans les liens
indexContent = indexContent.replace(/\?v=v\d+\.\d+\.\d+/g, `?v=${VERSION_WITH_V}`);
fs.writeFileSync(indexPath, indexContent);
console.log('✅ index.html mis à jour');

console.log(`\n✅ Version mise à jour avec succès vers ${VERSION_WITH_V}`);
console.log('\n📝 N\'oubliez pas de:');
console.log('   1. Vérifier que tous les fichiers sont correctement mis à jour');
console.log('   2. Tester l\'application après le déploiement');
console.log('   3. Vérifier que les icônes se mettent à jour correctement');

