"""
x402 Email Validator — validation approfondie d'emails
- Syntaxe RFC 5321
- DNS MX lookup
- Détection d'adresses jetables (blacklist ~200 domaines)
- Score de délivrabilité estimé
"""
from __future__ import annotations
import os, re, json
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import dns.resolver
import dns.exception
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import httpx

load_dotenv()

WALLET  = os.getenv("WALLET_ADDRESS", "0x6458941857a70C6cA18c440a316035A21901A12b")
PRICE_ATOMIC = os.getenv("PRICE_ATOMIC", "1000")   # 0.001 USDC en µUSDC
FACILITATOR  = os.getenv("FACILITATOR_URL", "https://api.cdp.coinbase.com/platform/v2/x402")
USDC_BASE    = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"

payments_total = 0
payments_log: list = []

# ── Disposable email domains (liste partielle — ~200 domaines connus) ─────────
DISPOSABLE = {
    "mailinator.com","guerrillamail.com","guerrillamail.net","guerrillamail.org",
    "guerrillamail.biz","guerrillamail.de","guerrillamail.info","guerrillamail.com",
    "trashmail.com","trashmail.me","trashmail.net","trashmail.at","trashmail.io",
    "tempmail.com","tempmail.net","temp-mail.org","temp-mail.io","temp-mail.ru",
    "yopmail.com","yopmail.fr","yopmail.net","yopmail.pp.ua","yopmail.gq",
    "throwam.com","throwam.net","throwam.org",
    "sharklasers.com","guerrillamailblock.com","grr.la","guerrillamail.info",
    "spam4.me","spamgourmet.com","spamgourmet.net","spamgourmet.org",
    "maildrop.cc","mailnull.com","mailnesia.com","mailnull.com",
    "dispostable.com","spamevader.net","trashmail.org","trashmail.me",
    "throwam.com","trbvm.com","fakeinbox.com","inboxbear.com",
    "mailnull.com","mailnesia.com","spam4.me","s0ny.net",
    "mailexpire.com","mailnull.com","mailnull.com","mailnull.com",
    "10minutemail.com","10minutemail.net","10minutemail.org","10minutemail.de",
    "10minutemail.co.uk","10minutemail.cf","10minutemail.ga","10minutemail.ml",
    "20minutemail.com","20minutemail.it","30minutemail.com",
    "filzmail.com","getairmail.com","getonemail.com","getonemail.net",
    "gishpuppy.com","harakirimail.com","hatespam.org","hidemail.de",
    "incognitomail.com","incognitomail.net","incognitomail.org",
    "inoutmail.com","inoutmail.de","inoutmail.eu","inoutmail.info",
    "instant-mail.de","instantemailaddress.com","jetable.com","jetable.fr.nf",
    "jetable.net","jetable.org","landmail.co","lroid.com",
    "mailandftp.com","mailbidon.com","mailblocks.com","mailbucket.org",
    "mailcat.biz","mailcatch.com","mailchop.com","mailcker.com",
    "mailde.net","maildrop.cc","maileater.com","maileimer.de",
    "mailexpire.com","mailfa.tk","mailforspam.com","mailfree.ml",
    "mailguard.me","mailhazard.com","mailhazard.us","mailimate.com",
    "mailimm.com","mailinator.gq","mailinator.net","mailinator.org",
    "mailinator.us","mailinator2.com","mailincubator.com","mailinater.com",
    "mailismagic.com","mailme.ir","mailme.lv","mailme24.com",
    "mailmetrash.com","mailmoat.com","mailnew.com","mailnull.com",
    "mailpoof.com","mailproxsy.com","mailrock.biz","mailrubbish.com",
    "mailscrap.com","mailshell.net","mailsiphon.com","mailslapping.com",
    "mailslite.com","mailsponge.com","mailtemp.net","mailtome.de",
    "mailtothis.com","mailtrash.net","mailtrix.net","mailzilla.com",
    "makemetheking.com","manybrain.com","mega.zik.dj","meinspamschutz.de",
    "meltmail.com","messagebeamer.de","mierdamail.com","mintemail.com",
    "moburl.com","monemail.fr.nf","myfastmail.com","myfunnymail.com",
    "mymail-in.net","myphantomemail.com","myspamless.com","mytempemail.com",
    "mytempmail.com","mytrashmail.com","mywarnmail.com","netzidiot.de",
    "nincsmail.hu","no-spam.ws","nobulk.com","noclickemail.com",
    "nomail.pw","nomail.xl.cx","nomail2me.com","nomorespamemails.com",
    "nonspam.eu","nonspammer.de","nospam.ze.tc","nospam4.us",
    "nospamfor.us","nospammail.net","nospamthanks.info","notmailinator.com",
    "notsharingmy.info","null.net","obobbo.com","onewaymail.com",
    "online.ms","oopi.org","owlpic.com","pecinan.com",
    "pecinan.net","pecinan.org","pepbot.com","pfui.ru",
    "phentermine-mortgages-porn.com","pimpedupmyspace.com","plexolan.de",
    "pookmail.com","privatdemail.net","privy-mail.com","proxymail.eu",
    "prtnx.com","putthisinyourspamdatabase.com","qq.com","qsl.ro",
    "quickinbox.com","rcpt.at","reallymymail.com","recursor.net",
    "reddithub.com","regbypass.comsafe-mail.net","regbypass.com",
    "rhyta.com","safetymail.info","safetypost.de","saucelabs.com",
    "schafmail.de","schrott-email.de","secretemail.de","secure-mail.biz",
    "senseless-entertainment.com","sent.as","services391.com","sharedmailbox.org",
    "sharklasers.com","shieldemail.com","shiftmail.com","shitmail.me",
    "shitware.nl","shmeriously.com","shortmail.net","sibmail.com",
    "smellfear.com","smsoffice.net","sogetthis.com","sofort-mail.de",
    "sofortmail.de","spam.la","spam.mn","spam.su","spam4.me",
    "spamavert.com","spambob.com","spambob.net","spambob.org",
    "spambox.info","spambox.irishspringrealty.com","spambox.us",
    "spamcannon.com","spamcannon.net","spamcero.com","spamcon.org",
    "spamcorptastic.com","spamday.com","spamex.com","spamfree.eu",
    "spamgob.com","spamgourmet.com","spamgourmet.net","spamgourmet.org",
    "spamgourmet.com","spamherelots.com","spamhereplease.com",
    "spamify.com","spaminator.de","spamkill.info","spammotel.com",
    "spamoff.de","spamslicer.com","spamspot.com","spamthis.co.uk",
    "spamtroll.net","speed.1s.fr","spr.io","startkeys.com",
    "stexsy.com","stuffmail.de","supergreatmail.com","supermailer.jp",
    "superrito.com","superstachel.de","suremail.info","svk.jp",
    "sweetxxx.de","tafmail.com","tagyourself.com","tapchicuocsong.com",
    "tembel.org","tempail.com","tempalias.com","tempe-mail.com",
    "tempemail.biz","tempemail.co.za","tempemail.com","tempemail.net",
    "tempemail.org","tempinbox.co.uk","tempinbox.com","tempmail.de",
    "tempmail.eu","tempmail.it","tempmail.org","tempmail.us",
    "tempmail2.com","tempmailer.com","tempmailer.de","tempomail.fr",
    "temporaryemail.net","temporaryemail.us","temporaryforwarding.com",
    "temporaryinbox.com","temporarymail.org","tempr.email","tempsky.com",
    "tempthe.net","tempymail.com","thankyou2010.com","thc.st",
    "thecloudindex.com","thelimestones.com","thisisnotmyrealemail.com",
    "thismail.net","throwam.com","throwam.net","throwam.org",
    "throwassaway.com","throwaway.email","throwam.com","tilien.com",
    "tmailinator.com","tmailinator.net","toiea.com","toomail.biz",
    "topranklist.de","tradermail.info","trash-amil.com","trash-mail.at",
    "trash-mail.cf","trash-mail.ga","trash-mail.gq","trash-mail.io",
    "trash-mail.ml","trash-mail.net","trash-mail.tk",
    "trash2009.com","trashdevil.com","trashdevil.de","trashemail.de",
    "trashmail.app","trashmail.at","trashmail.com","trashmail.de",
    "trashmail.es","trashmail.eu","trashmail.fr","trashmail.io",
    "trashmail.me","trashmail.net","trashmail.org","trashmailer.com",
    "trashmail.at","trashmail.me",
}

# ── RFC 5321 email regex ──────────────────────────────────────────────────────
EMAIL_RE = re.compile(
    r'^[a-zA-Z0-9.!#$%&\'*+/=?^_`{|}~-]+'
    r'@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?'
    r'(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*'
    r'\.[a-zA-Z]{2,}$'
)


def validate_email(email: str) -> dict:
    email = email.strip().lower()

    # 1. Syntaxe
    if not EMAIL_RE.match(email):
        return {"valid": False, "email": email, "syntax_ok": False,
                "mx_records": [], "is_disposable": False, "score": 0.0,
                "reason": "Syntaxe RFC 5321 invalide"}

    domain = email.split("@")[1]

    # 2. Domaine jetable
    is_disposable = domain in DISPOSABLE

    # 3. MX records
    mx_records = []
    mx_error = None
    try:
        answers = dns.resolver.resolve(domain, "MX", lifetime=5)
        mx_records = sorted(
            [str(r.exchange).rstrip(".") for r in answers],
            key=lambda x: x
        )
    except dns.resolver.NXDOMAIN:
        mx_error = "Domaine inexistant (NXDOMAIN)"
    except dns.resolver.NoAnswer:
        mx_error = "Aucun enregistrement MX"
    except dns.exception.Timeout:
        mx_error = "Timeout DNS"
    except Exception as e:
        mx_error = f"Erreur DNS: {e}"

    has_mx = len(mx_records) > 0

    # 4. Score de délivrabilité
    score = 1.0
    if is_disposable:
        score -= 0.5
    if not has_mx:
        score -= 0.4
    if mx_error:
        score -= 0.1
    score = round(max(0.0, min(1.0, score)), 2)

    valid = has_mx and not is_disposable
    result = {
        "valid": valid,
        "email": email,
        "domain": domain,
        "syntax_ok": True,
        "mx_records": mx_records[:5],
        "is_disposable": is_disposable,
        "score": score,
    }
    if mx_error:
        result["mx_error"] = mx_error
    return result


# ── x402 setup ───────────────────────────────────────────────────────────────

PAYMENT_REQUIREMENTS = {
    "scheme": "exact",
    "network": "base",
    "maxAmountRequired": PRICE_ATOMIC,
    "resource": "https://x402-email.suretat.com/validate",
    "description": "Validation email approfondie — DNS MX + détection jetables",
    "mimeType": "application/json",
    "payTo": WALLET,
    "maxTimeoutSeconds": 300,
    "asset": USDC_BASE,
    "extra": {
        "name": "USD Coin",
        "version": "2",
        "bazaar": {
            "bodyType": "json",
            "input": {"email": "user@example.com"},
            "inputSchema": {
                "properties": {
                    "email": {"type": "string", "description": "Adresse email à valider"}
                },
                "required": ["email"],
            },
            "output": {
                "example": {
                    "valid": True,
                    "email": "user@example.com",
                    "domain": "example.com",
                    "syntax_ok": True,
                    "mx_records": ["mail.example.com"],
                    "is_disposable": False,
                    "score": 0.95,
                }
            },
        },
    },
}


async def cdp_call(endpoint: str, payment_header: str) -> bool:
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(
                f"{FACILITATOR}/{endpoint}",
                json={
                    "x402Version": 1,
                    "paymentHeader": payment_header,
                    "paymentRequirements": [PAYMENT_REQUIREMENTS],
                },
            )
            if endpoint == "verify":
                return resp.json().get("isValid", False)
            return resp.status_code == 200
        except Exception:
            return False


@asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"[x402-email] Wallet: {WALLET}")
    print(f"[x402-email] Price: {PRICE_ATOMIC} µUSDC (0.001 USDC)")
    yield


app = FastAPI(title="x402 Email Validator", version="1.0.0", lifespan=lifespan)


class EmailRequest(BaseModel):
    email: str


@app.middleware("http")
async def x402_middleware(request: Request, call_next):
    if not request.url.path.startswith("/validate"):
        return await call_next(request)

    payment_header = request.headers.get("X-PAYMENT")
    if not payment_header:
        return JSONResponse(
            status_code=402,
            content={"x402Version": 1, "accepts": [PAYMENT_REQUIREMENTS], "error": "Payment required"},
                    headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "no-store"},
        )

    if not await cdp_call("verify", payment_header):
        return JSONResponse(
            status_code=402,
            content={"x402Version": 1, "error": "Paiement invalide ou expiré"},
                    headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "no-store"},
        )

    response = await call_next(request)

    await cdp_call("settle", payment_header)
    global payments_total, payments_log
    payments_total += 1
    payments_log.append({
        "n": payments_total,
        "at": datetime.now(timezone.utc).isoformat(),
    })
    if len(payments_log) > 100:
        payments_log = payments_log[-100:]
    print(f"[x402-email] PAIEMENT #{payments_total}")
    return response


@app.get("/")
async def root():
    return {
        "service": "x402 Email Validator",
        "protocol": "x402 (Base/USDC)",
        "version": "1.0.0",
        "price": "0.001 USDC/appel",
        "endpoint": "POST /validate",
        "body": {"email": "user@example.com"},
        "checks": ["syntaxe RFC 5321", "DNS MX lookup", "détection jetables", "score délivrabilité"],
        "docs": "/docs",
        "tagline": "Validate email addresses — syntax, MX records, disposable domain detection",
        "curl_example": "curl https://x402-email-validator.suretat.com/validate -H 'Content-Type: application/json' -d '{\"email\": \"user@example.com\", \"check_mx\": true}'",
        "try_it": "https://x402-email-validator.suretat.com/docs",
    }


@app.post("/validate")
async def validate(payload: EmailRequest):
    if not payload.email or not payload.email.strip():
        return JSONResponse(status_code=400, content={"error": "Champ 'email' requis"})
    return validate_email(payload.email)


@app.get("/stats")
async def stats():
    return {
        "service": "x402-email-validator",
        "payments_total": payments_total,
        "last_payments": payments_log[-10:],
    }

@app.get("/.well-known/x402.json")
async def x402_well_known():
    return {"x402Version": 1, "accepts": [PAYMENT_REQUIREMENTS]}

@app.get("/.well-known/x402")
async def x402_well_known_redirect():
    from fastapi.responses import RedirectResponse
    return RedirectResponse("/.well-known/x402.json")

