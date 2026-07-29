// Lag en bcrypt-hash av et passord, til bruk i users.json / USERS.
// Bruk:  npm run hash-passord -- "det-hemmelige-passordet"
import bcrypt from "bcryptjs";

const passord = process.argv[2];
if (!passord) {
  console.error('Bruk: npm run hash-passord -- "passordet-ditt"');
  process.exit(1);
}
const hash = bcrypt.hashSync(passord, 10);
console.log(hash);
