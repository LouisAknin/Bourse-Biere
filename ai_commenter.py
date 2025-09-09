# ====================== AI market footer (OpenRouter) ============================
# Dépendances: requests (pip install requests)
import os, json, time, threading, requests
from datetime import datetime, timezone
import pandas as pd
import numpy as np
import math
from dotenv import load_dotenv

# Load env variables
load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL")

HISTORY_PATH = "ai_market_comments.json"  # persiste l'historique
MAX_HISTORY = 15
SERIES_POINTS = 40      # nb de points 'Close' par bière envoyés à l'IA
THROTTLE_SECONDS = 30   # délai mini entre deux requêtes IA

def dfs_from_l_bieres(l_bieres):
    """Construit un dict {nom_biere: df} depuis ta liste d'objets."""
    return {b.nom: b.df for b in l_bieres}

def _safe_num(x, ndigits=None):
    """Retourne None si x n'est pas un nombre fini; sinon arrondi optionnel."""
    if x is None:
        return None
    try:
        xf = float(x)
    except Exception:
        return None
    if not math.isfinite(xf):
        return None
    if ndigits is not None:
        return round(xf, ndigits)
    return xf

def _pct(now_val, past_val):
    if now_val is None or past_val is None:
        return None
    if past_val == 0:
        return None
    try:
        r = (now_val - past_val) / abs(past_val) * 100.0
    except Exception:
        return None
    return r

def build_ai_payload_from_dfs(dfs: dict, history:list=None,
                              series_points:int=40, round_dec:int=3):
    """
    dfs: {"Corona": df_corona, ...} avec colonnes Open,High,Low,Close,Volume et index datetime
    Retourne un dict JSON-serializable SANS NaN/Inf.
    """
    payload = {
        "schema": "beer-market-v1",
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "series_points": series_points,
        "beers": [],
        "history": (history or [])[-15:]
    }

    for name, df in dfs.items():
        if df is None or len(df) == 0:
            continue

        d = df.copy()

        # Colonnes attendues (tolère minuscules)
        for col in ["Open","High","Low","Close","Volume"]:
            if col not in d.columns:
                lower_map = {c.lower(): c for c in d.columns}
                if col.lower() in lower_map:
                    d.rename(columns={lower_map[col.lower()]: col}, inplace=True)

        # Index datetime en UTC, tri
        if not isinstance(d.index, pd.DatetimeIndex):
            d.index = pd.to_datetime(d.index, errors="coerce", utc=True)
        else:
            d.index = d.index.tz_localize("UTC") if d.index.tz is None else d.index.tz_convert("UTC")
        d = d.sort_index()

        # Ne garder que l’essentiel et nettoyer Inf/NaN
        d = d[["Open","High","Low","Close","Volume"]].astype(float)
        d.replace([np.inf, -np.inf], np.nan, inplace=True)
        d.dropna(subset=["Close"], inplace=True)

        tail = d.tail(series_points)
        if len(tail) < 2:
            continue

        closes = tail["Close"].astype(float)
        last = _safe_num(closes.iloc[-1], round_dec)

        # Variations %
        def at_offset(n):
            return _safe_num(closes.iloc[-n]) if len(closes) >= n else None

        ch_1  = _pct(_safe_num(closes.iloc[-1]), at_offset(2))
        ch_5  = _pct(_safe_num(closes.iloc[-1]), at_offset(6))
        ch_30 = _pct(_safe_num(closes.iloc[-1]), at_offset(min(31, len(closes))))

        ch_1  = _safe_num(ch_1, 2)
        ch_5  = _safe_num(ch_5, 2)
        ch_30 = _safe_num(ch_30, 2)

        # Volatilité (std des rendements) ; peut être NaN si 0/1 point ⇒ safe
        ret = closes.pct_change().replace([np.inf, -np.inf], np.nan).dropna()
        vol = _safe_num(ret.std(), 3)

        # Série compacte time/close (on saute les points non finis)
        series = []
        for idx, val in closes.items():
            c = _safe_num(val, round_dec)
            if c is None:
                continue
            ts = idx.isoformat(timespec="seconds")
            series.append({"t": ts, "c": c})

        if not series:
            continue

        payload["beers"].append({
            "name": str(name),
            "features": {
                "last": last,
                "ch_1": ch_1,
                "ch_5": ch_5,
                "ch_30": ch_30,
                "vol": vol
            },
            "series": series
        })

    return payload


"""
def build_ai_payload_from_dfs(dfs: dict, history:list=None,
                              series_points:int=SERIES_POINTS, round_dec:int=3):
    """"""
    dfs: {"Corona": df_corona, ...} avec colonnes Open,High,Low,Close,Volume et index datetime
    Retourne un dict JSON-serializable compact pour le LLM.
    """"""
    payload = {
        "schema": "beer-market-v1",
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "series_points": series_points,
        "beers": [],
        "history": (history or [])[-MAX_HISTORY:]
    }

    for name, df in dfs.items():
        if df is None or len(df) == 0:
            continue

        d = df.copy()
        # normalise colonnes si nécessaires (tolère minuscules)
        for col in ["Open","High","Low","Close","Volume"]:
            if col not in d.columns:
                lower_map = {c.lower(): c for c in d.columns}
                if col.lower() in lower_map:
                    d.rename(columns={lower_map[col.lower()]: col}, inplace=True)

        # index datetime -> UTC ISO
        if not isinstance(d.index, pd.DatetimeIndex):
            d.index = pd.to_datetime(d.index, errors="coerce", utc=True)
        else:
            # si index naïf, on considère UTC (ajuste ici si tu veux Europe/Paris)
            d.index = d.index.tz_localize("UTC", nonexistent="shift_forward", ambiguous="NaT") if d.index.tz is None else d.index.tz_convert("UTC")
        d = d.sort_index()

        d = d[["Open","High","Low","Close","Volume"]].dropna(subset=["Close"])
        tail = d.tail(series_points)
        if len(tail) < 2:
            continue

        closes = tail["Close"].astype(float)
        last = float(round(closes.iloc[-1], round_dec))

        def pct(a, b):
            if b is None or b == 0: return None
            return (a - b) / abs(b) * 100.0

        def at_offset(n):
            return float(closes.iloc[-n]) if len(closes) >= n else None

        ch_1  = pct(last, at_offset(2))
        ch_5  = pct(last, at_offset(6))
        ch_30 = pct(last, at_offset(min(31, len(closes))))

        ret = closes.pct_change().dropna()
        vol = float(round(ret.std(), 3)) if len(ret) else 0.0

        series = [{"t": idx.isoformat(timespec="seconds"),
                   "c": float(round(val, round_dec))}
                  for idx, val in closes.items()]

        payload["beers"].append({
            "name": str(name),
            "features": {
                "last": last,
                "ch_1": None if ch_1 is None else round(ch_1, 2),
                "ch_5": None if ch_5 is None else round(ch_5, 2),
                "ch_30": None if ch_30 is None else round(ch_30, 2),
                "vol": vol
            },
            "series": series
        })

    return payload"""



class AICommenter:
    def __init__(self, model=OPENROUTER_MODEL, api_key=OPENROUTER_API_KEY,
                 history_path=HISTORY_PATH, max_history=MAX_HISTORY):
        self.model = model
        self.api_key = api_key
        self.history_path = history_path
        self.max_history = max_history
        self._busy = False
        self._last_ts = 0
        self._history = self._load_history()

    def update_footer_async(self, root, footer_label, dfs:dict):
        """Appelle l'IA en thread puis met à jour le footer via root.after()."""
        now = time.time()
        if self._busy or (now - self._last_ts) < THROTTLE_SECONDS:
            return
        self._busy = True
        self._last_ts = now

        def worker():
            try:
                payload = build_ai_payload_from_dfs(dfs, history=self._history)
                comment = self._call_openrouter(payload)
                print("---------------------------------")
                print(comment)
                print("---------------------------------")
                if comment:
                    self._push_history(comment)
                    root.after(0, lambda c=comment: footer_label.config(text=c))
            except Exception as e:

                print(e)

                msg = f"IA: {e}"
                root.after(0, lambda m=msg: footer_label.config(text=m))
            finally:
                self._busy = False


        threading.Thread(target=worker, daemon=True).start()

    def _call_openrouter(self, payload: dict) -> str:
        if not self.api_key or self.api_key == "YOUR_OPENROUTER_API_KEY":
            raise RuntimeError("OPENROUTER_API_KEY manquant ou invalide")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            # Optionnels mais utiles pour OpenRouter
            "HTTP-Referer": "https://shhark.local",
            "X-Title": "Shhark Beer Market",
        }

        body = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Tu es \"Shhark\", le commentateur officiel d’un faux marché boursier de bières "
                        "pendant une soirée d’ingénieurs.\n\n"
                        "Règles :\n"
                        "- Langue : 100% français, argot et trash autorisés. Pas de censure.\n"
                        "- Style : commentateur sportif en roue libre, mélange d’analyse financière et de stand-up de comptoir.\n"
                        "- Longueur : 2–3 phrases max.\n"
                        "- Contenu : analyse du marché des bières (hausse, baisse, volatilité, leaders/laggards), "
                        "+ punchlines drôles, + call-to-action implicite (« allez boire », « foncez sur »).\n"
                        "- Chiffres : tu peux citer des variations %, prix, ou volatilité pour rendre ça réaliste.\n"
                        "- Humour : fais rire, pousse dans l’absurde si tu veux. "
                        "Tu peux glisser des blagues random sans rapport (rarement, 1 fois sur 10).\n"
                        "- Variabilité : ne pas répéter la même tournure à chaque fois. Alterne entre hype, ironie, "
                        "blagues salaces, délires hallucinés.\n"
                        "- Objectif : mettre l’ambiance et inciter les gens à jouer le jeu. Tout est permis sauf la censure.\n"
                        "- Si rien d’intéressant ne se passe sur le marché, invente un délire "
                        "(ex : hallucination, commentaire absurde, théorie du complot sur les bières)."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        payload, ensure_ascii=False, allow_nan=False, separators=(",", ":")
                    ),
                },
            ],
            "temperature": 0.9,   # j’ai augmenté un peu pour plus de variété
            "max_tokens": 180,
        }

        try:
            r = requests.post(OPENROUTER_URL, headers=headers, json=body, timeout=30)
        except requests.RequestException as net_err:
            # erreur réseau claire
            raise RuntimeError(f"réseau: {net_err}")

        # Si status != 2xx, on remonte un message parlant + snippet de la réponse
        if not (200 <= r.status_code < 300):
            txt = r.text.strip()
            snippet = txt[:300].replace("\n", " ")
            raise RuntimeError(f"HTTP {r.status_code}: {snippet}")

        # Parfois OpenRouter renvoie du vide ou du HTML => protéger r.json()
        raw = r.text.strip()
        if not raw:
            raise RuntimeError("réponse vide de l'API")
        # Vérifie le Content-Type quand il existe
        ctype = r.headers.get("Content-Type", "")
        if "application/json" not in ctype.lower():
            snippet = raw[:300].replace("\n", " ")
            raise RuntimeError(f"réponse non-JSON: {snippet}")

        try:
            data = r.json()
        except ValueError:
            # r.json() a échoué (ton erreur actuelle)
            snippet = raw[:300].replace("\n", " ")
            raise RuntimeError(f"parse JSON: {snippet}")

        try:
            text = data["choices"][0]["message"]["content"].strip()
        except Exception:
            raise RuntimeError(f"JSON inattendu: {data}")

        if not text:
            raise RuntimeError("réponse vide (choices[0].message.content)")

        return text


    def _load_history(self):
        try:
            with open(self.history_path, "r", encoding="utf-8") as f:
                h = json.load(f)
            return h[-self.max_history:] if isinstance(h, list) else []
        except Exception:
            return []

    def _push_history(self, comment: str):
        self._history.append(comment)
        self._history = self._history[-self.max_history:]
        try:
            with open(self.history_path, "w", encoding="utf-8") as f:
                json.dump(self._history, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
# =================== /AI market footer (OpenRouter) ===============================
