// Redaktør-assistent – proxy-server.
//
// To endepunkter:
//   POST /login   { brukernavn, passord }         -> { token }
//   POST /review  { text }  (Authorization: Bearer) -> strukturert vurdering (JSON)
//
// Claude-nøkkelen leses fra miljøvariabelen ANTHROPIC_API_KEY og forlater
// aldri serveren. Kun forespørsler med gyldig token slipper gjennom /review.

import "dotenv/config";
import express from "express";
import cors from "cors";
import jwt from "jsonwebtoken";
import bcrypt from "bcryptjs";
import rateLimit from "express-rate-limit";
import { readFileSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import Anthropic from "@anthropic-ai/sdk";
import { SYSTEM_PROMPT, REVIEW_SCHEMA } from "./prompt.js";

const __dirname = dirname(fileURLToPath(import.meta.url));

// ---- Konfigurasjon ---------------------------------------------------------

const PORT = process.env.PORT || 8787;
const MODEL = process.env.MODEL || "claude-opus-4-8";
const JWT_SECRET = process.env.JWT_SECRET;
const ANTHROPIC_API_KEY = process.env.ANTHROPIC_API_KEY;
const TOKEN_TTL = process.env.TOKEN_TTL || "12h";
// Maks lengde på artikkelteksten (tegn) – hindrer utilsiktet store kall.
const MAX_TEXT_LENGTH = Number(process.env.MAX_TEXT_LENGTH || 60000);

if (!ANTHROPIC_API_KEY) {
  console.error("FEIL: ANTHROPIC_API_KEY er ikke satt i miljøet.");
  process.exit(1);
}
if (!JWT_SECRET) {
  console.error("FEIL: JWT_SECRET er ikke satt i miljøet (bruk en lang, tilfeldig streng).");
  process.exit(1);
}

// Brukere lastes fra USERS (JSON i miljøvariabel) eller users.json.
// Format: [{ "brukernavn": "mathias", "passordHash": "$2a$..." }]
function lastBrukere() {
  if (process.env.USERS) {
    try {
      return JSON.parse(process.env.USERS);
    } catch {
      console.error("FEIL: USERS er ikke gyldig JSON.");
      process.exit(1);
    }
  }
  const fil = join(__dirname, "users.json");
  if (existsSync(fil)) {
    return JSON.parse(readFileSync(fil, "utf8"));
  }
  console.error(
    "FEIL: Ingen brukere funnet. Sett USERS-miljøvariabelen eller lag server/users.json.\n" +
      "Lag en hash med:  npm run hash-passord -- \"passordet-ditt\""
  );
  process.exit(1);
}

const BRUKERE = lastBrukere();
const anthropic = new Anthropic({ apiKey: ANTHROPIC_API_KEY });

// ---- App -------------------------------------------------------------------

const app = express();
app.use(cors()); // token-basert tilgang, så åpen CORS er greit
app.use(express.json({ limit: "1mb" }));

// Enkel rate-limiting.
const loginLimiter = rateLimit({ windowMs: 15 * 60 * 1000, max: 30 });
const reviewLimiter = rateLimit({ windowMs: 60 * 1000, max: 20 });

app.get("/", (_req, res) => {
  res.json({ ok: true, tjeneste: "redaktor-assistent", modell: MODEL });
});

// ---- Innlogging ------------------------------------------------------------

app.post("/login", loginLimiter, async (req, res) => {
  const { brukernavn, passord } = req.body || {};
  if (!brukernavn || !passord) {
    return res.status(400).json({ feil: "Mangler brukernavn eller passord." });
  }
  const bruker = BRUKERE.find((b) => b.brukernavn === brukernavn);
  // Sammenlign alltid mot en hash for å unngå timing-lekkasje om brukeren finnes.
  const hash = bruker?.passordHash || "$2a$10$invalidinvalidinvalidinvalidinvalidinvalidin";
  const ok = await bcrypt.compare(passord, hash);
  if (!bruker || !ok) {
    return res.status(401).json({ feil: "Feil brukernavn eller passord." });
  }
  const token = jwt.sign({ sub: brukernavn }, JWT_SECRET, { expiresIn: TOKEN_TTL });
  res.json({ token, brukernavn });
});

// Middleware: krev gyldig token.
function krevToken(req, res, next) {
  const auth = req.headers.authorization || "";
  const token = auth.startsWith("Bearer ") ? auth.slice(7) : null;
  if (!token) return res.status(401).json({ feil: "Mangler token. Logg inn på nytt." });
  try {
    req.bruker = jwt.verify(token, JWT_SECRET);
    next();
  } catch {
    return res.status(401).json({ feil: "Ugyldig eller utløpt token. Logg inn på nytt." });
  }
}

// ---- Kvalitetskontroll -----------------------------------------------------

app.post("/review", reviewLimiter, krevToken, async (req, res) => {
  const text = (req.body?.text || "").toString();
  if (!text.trim()) {
    return res.status(400).json({ feil: "Ingen tekst mottatt." });
  }
  if (text.length > MAX_TEXT_LENGTH) {
    return res.status(413).json({
      feil: `Teksten er for lang (${text.length} tegn, maks ${MAX_TEXT_LENGTH}).`
    });
  }

  try {
    // Streamer internt for å unngå HTTP-timeout på lange svar; nettleseren
    // får hele JSON-resultatet i én respons.
    const stream = anthropic.messages.stream({
      model: MODEL,
      max_tokens: 32000,
      thinking: { type: "adaptive" },
      output_config: {
        effort: "high",
        format: { type: "json_schema", schema: REVIEW_SCHEMA }
      },
      system: SYSTEM_PROMPT,
      messages: [
        {
          role: "user",
          content:
            "Gjennomfør en fullstendig redaksjonell kvalitetskontroll av denne artikkelen. " +
            "Svar kun i det oppgitte JSON-formatet.\n\n<artikkel>\n" +
            text +
            "\n</artikkel>"
        }
      ]
    });

    const message = await stream.finalMessage();

    if (message.stop_reason === "refusal") {
      return res.status(422).json({ feil: "Modellen avslo å behandle teksten." });
    }

    const tekstblokk = message.content.find((b) => b.type === "text");
    if (!tekstblokk) {
      return res.status(502).json({ feil: "Fikk ikke noe tekstsvar fra modellen." });
    }

    let data;
    try {
      data = JSON.parse(tekstblokk.text);
    } catch {
      return res.status(502).json({ feil: "Klarte ikke tolke svaret fra modellen som JSON." });
    }

    res.json({ resultat: data, modell: message.model });
  } catch (err) {
    const status = err?.status || 500;
    console.error("Feil mot Claude:", err?.message || err);
    if (status === 429) {
      return res.status(429).json({ feil: "For mange forespørsler mot modellen. Prøv igjen om litt." });
    }
    res.status(502).json({ feil: "Noe gikk galt ved kontrollen. Prøv igjen." });
  }
});

app.listen(PORT, () => {
  console.log(`Redaktør-assistent kjører på port ${PORT} (modell: ${MODEL})`);
});
