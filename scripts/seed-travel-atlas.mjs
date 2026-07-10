import { readFileSync } from 'node:fs';
import { initializeApp } from 'firebase/app';
import { getDatabase, ref, push, set } from 'firebase/database';
import { getStorage, ref as sref, uploadBytes, getDownloadURL } from 'firebase/storage';

const [,, dbUrl, bucket] = process.argv;
if (!dbUrl || !bucket) {
  console.error('Usage: node scripts/seed-travel-atlas.mjs <databaseURL> <storageBucket>');
  process.exit(1);
}

const app = initializeApp({ databaseURL: dbUrl, storageBucket: bucket });
const db = getDatabase(app);
const storage = getStorage(app);

const trips = JSON.parse(readFileSync(new URL('../seed-data/travel-atlas-seed.json', import.meta.url)));

for (const trip of trips) {
  const { entries = [], ...tripFields } = trip;
  const tripRef = push(ref(db, '/trips'));
  await set(tripRef, tripFields);
  console.log(`Trip created: ${trip.title} (${tripRef.key})`);

  for (const entry of entries) {
    const { localPhotoPaths = [], ...entryFields } = entry;
    const photoUrls = [];
    for (const localPath of localPhotoPaths) {
      const bytes = readFileSync(new URL(`../${localPath}`, import.meta.url));
      const fileRef = sref(storage, `trips/${tripRef.key}/entries/seed-${Date.now()}-${localPath.split('/').pop()}`);
      await uploadBytes(fileRef, bytes);
      photoUrls.push(await getDownloadURL(fileRef));
    }
    const entryRef = push(ref(db, `/trips/${tripRef.key}/entries`));
    await set(entryRef, { ...entryFields, photos: photoUrls });
  }
}
console.log('Seed complete.');
