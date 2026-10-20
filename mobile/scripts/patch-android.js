// Ajustes del proyecto Android generado por Capacitor (se ejecuta tras `npx cap add android`):
//  1) Deep link miplan703://  → Strava devuelve aquí el código de autorización.
//  2) Solo orientación vertical y nombre visible de la app.
const fs = require('fs');
const path = require('path');

const manifest = path.join(__dirname, '..', 'android', 'app', 'src', 'main', 'AndroidManifest.xml');
let xml = fs.readFileSync(manifest, 'utf8');

const filtro = `
            <intent-filter android:autoVerify="false">
                <action android:name="android.intent.action.VIEW" />
                <category android:name="android.intent.category.DEFAULT" />
                <category android:name="android.intent.category.BROWSABLE" />
                <data android:scheme="miplan703" />
            </intent-filter>`;
if (!xml.includes('android:scheme="miplan703"')) {
  // dentro de la MainActivity, justo después de su intent-filter LAUNCHER
  const i = xml.indexOf('</intent-filter>', xml.indexOf('android.intent.category.LAUNCHER'));
  if (i < 0) throw new Error('No se encontró el intent-filter LAUNCHER en AndroidManifest.xml');
  xml = xml.slice(0, i + '</intent-filter>'.length) + filtro + xml.slice(i + '</intent-filter>'.length);
}
if (!xml.includes('android:screenOrientation')) {
  xml = xml.replace('android:name=".MainActivity"', 'android:name=".MainActivity"\n            android:screenOrientation="portrait"');
}
fs.writeFileSync(manifest, xml);

const strings = path.join(__dirname, '..', 'android', 'app', 'src', 'main', 'res', 'values', 'strings.xml');
if (fs.existsSync(strings)) {
  let s = fs.readFileSync(strings, 'utf8');
  s = s.replace(/<string name="app_name">[^<]*<\/string>/, '<string name="app_name">Mi plan 70.3</string>')
       .replace(/<string name="title_activity_main">[^<]*<\/string>/, '<string name="title_activity_main">Mi plan 70.3</string>');
  fs.writeFileSync(strings, s);
}
console.log('AndroidManifest: deep link miplan703:// y orientación vertical aplicados');
