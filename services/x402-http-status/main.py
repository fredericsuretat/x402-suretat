from __future__ import annotations
import os, time
import uvicorn
from fastapi import FastAPI, Request, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional
import httpx

PRICE_ATOMIC = os.getenv("PRICE_ATOMIC", "500")
PAY_TO = os.getenv("PAY_TO", "0x6458941857a70C6cA18c440a316035A21901A12b")
NETWORK = os.getenv("NETWORK", "base")
ASSET_ADDRESS = os.getenv("ASSET_ADDRESS", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")

stats = {"total_paid": 0, "revenue_usdc": 0.0, "start_time": time.time()}
app = FastAPI(title="x402 HTTP Status", version="1.0.0")

HTTP_CODES = {
    # 1xx Informational
    100: {"name_en": "Continue", "name_fr": "Continuer", "category": "informational",
          "description_en": "The server received the initial part of the request and the client should continue.",
          "description_fr": "Le serveur a reçu la requête initiale, le client peut continuer.",
          "rfc": "RFC 7231", "usage": "Used in HTTP/1.1 to continue a request after checking headers."},
    101: {"name_en": "Switching Protocols", "name_fr": "Changement de protocole", "category": "informational",
          "description_en": "The server agrees to switch protocols as requested by the client.",
          "description_fr": "Le serveur accepte de changer de protocole.",
          "rfc": "RFC 7231", "usage": "Used when upgrading to WebSocket or HTTP/2."},
    102: {"name_en": "Processing", "name_fr": "Traitement en cours", "category": "informational",
          "description_en": "The server has received and is processing the request, but no response is available yet.",
          "description_fr": "La requête est en cours de traitement.",
          "rfc": "RFC 2518 (WebDAV)", "usage": "Used in WebDAV to prevent request timeouts."},
    103: {"name_en": "Early Hints", "name_fr": "Indices précoces", "category": "informational",
          "description_en": "Used to return some response headers before final HTTP message.",
          "description_fr": "Retourne des en-têtes avant la réponse finale.",
          "rfc": "RFC 8297", "usage": "Used to preload resources while the server prepares the response."},
    # 2xx Success
    200: {"name_en": "OK", "name_fr": "Succès", "category": "success",
          "description_en": "The request succeeded.",
          "description_fr": "La requête a réussi.",
          "rfc": "RFC 7231", "usage": "Standard response for successful HTTP requests."},
    201: {"name_en": "Created", "name_fr": "Créé", "category": "success",
          "description_en": "The request succeeded and a new resource was created.",
          "description_fr": "La requête a réussi et une ressource a été créée.",
          "rfc": "RFC 7231", "usage": "Response to POST or PUT creating a new resource."},
    202: {"name_en": "Accepted", "name_fr": "Accepté", "category": "success",
          "description_en": "The request has been received but not yet acted upon.",
          "description_fr": "La requête a été reçue mais pas encore traitée.",
          "rfc": "RFC 7231", "usage": "Used for asynchronous operations."},
    203: {"name_en": "Non-Authoritative Information", "name_fr": "Information non autorisée", "category": "success",
          "description_en": "The returned metadata is from a copy, not the origin server.",
          "description_fr": "Les métadonnées proviennent d'une copie.",
          "rfc": "RFC 7231", "usage": "Used by proxies that modify responses."},
    204: {"name_en": "No Content", "name_fr": "Pas de contenu", "category": "success",
          "description_en": "The request succeeded but returns no content.",
          "description_fr": "La requête a réussi mais retourne aucun contenu.",
          "rfc": "RFC 7231", "usage": "Used for DELETE or PUT with no body response."},
    205: {"name_en": "Reset Content", "name_fr": "Réinitialiser le contenu", "category": "success",
          "description_en": "The server tells the client to reset the document view.",
          "description_fr": "Le serveur demande au client de réinitialiser la vue.",
          "rfc": "RFC 7231", "usage": "Used after form submission to clear the form."},
    206: {"name_en": "Partial Content", "name_fr": "Contenu partiel", "category": "success",
          "description_en": "The server delivers only part of the resource due to a range header.",
          "description_fr": "Le serveur retourne une partie de la ressource.",
          "rfc": "RFC 7233", "usage": "Used for resumable downloads and media streaming."},
    207: {"name_en": "Multi-Status", "name_fr": "Multi-statut", "category": "success",
          "description_en": "Conveys information about multiple resources.",
          "description_fr": "Donne des informations sur plusieurs ressources.",
          "rfc": "RFC 4918 (WebDAV)", "usage": "Used in WebDAV responses."},
    208: {"name_en": "Already Reported", "name_fr": "Déjà signalé", "category": "success",
          "description_en": "Members of a DAV binding have already been enumerated.",
          "description_fr": "Les membres ont déjà été énumérés.",
          "rfc": "RFC 5842", "usage": "Used in WebDAV to avoid listing members multiple times."},
    226: {"name_en": "IM Used", "name_fr": "IM utilisé", "category": "success",
          "description_en": "The server fulfilled a GET request using instance manipulations.",
          "description_fr": "Le serveur a utilisé des manipulations d'instance.",
          "rfc": "RFC 3229", "usage": "Used with HTTP delta encoding."},
    # 3xx Redirection
    300: {"name_en": "Multiple Choices", "name_fr": "Choix multiples", "category": "redirection",
          "description_en": "Multiple options for the resource are available.",
          "description_fr": "Plusieurs options sont disponibles pour la ressource.",
          "rfc": "RFC 7231", "usage": "Indicates multiple representations of a resource."},
    301: {"name_en": "Moved Permanently", "name_fr": "Déplacé de façon permanente", "category": "redirection",
          "description_en": "The requested resource has been permanently moved.",
          "description_fr": "La ressource a été déplacée de façon permanente.",
          "rfc": "RFC 7231", "usage": "SEO-friendly permanent redirect."},
    302: {"name_en": "Found", "name_fr": "Trouvé", "category": "redirection",
          "description_en": "The resource has temporarily moved.",
          "description_fr": "La ressource a temporairement bougé.",
          "rfc": "RFC 7231", "usage": "Temporary redirect, commonly used."},
    303: {"name_en": "See Other", "name_fr": "Voir autre", "category": "redirection",
          "description_en": "The response can be found at a different URI using GET.",
          "description_fr": "La réponse se trouve à une autre URI via GET.",
          "rfc": "RFC 7231", "usage": "Used after POST to redirect to a GET resource."},
    304: {"name_en": "Not Modified", "name_fr": "Non modifié", "category": "redirection",
          "description_en": "The resource has not been modified since the last request.",
          "description_fr": "La ressource n'a pas été modifiée depuis la dernière requête.",
          "rfc": "RFC 7232", "usage": "Used for conditional GET requests with caching."},
    305: {"name_en": "Use Proxy", "name_fr": "Utiliser le proxy", "category": "redirection",
          "description_en": "The resource must be accessed through a proxy.",
          "description_fr": "La ressource doit être accédée via un proxy.",
          "rfc": "RFC 7231", "usage": "Deprecated due to security concerns."},
    307: {"name_en": "Temporary Redirect", "name_fr": "Redirection temporaire", "category": "redirection",
          "description_en": "The resource has temporarily moved, preserving the HTTP method.",
          "description_fr": "La ressource a temporairement bougé, méthode HTTP préservée.",
          "rfc": "RFC 7231", "usage": "Temporary redirect preserving POST method."},
    308: {"name_en": "Permanent Redirect", "name_fr": "Redirection permanente", "category": "redirection",
          "description_en": "The resource has permanently moved, preserving the HTTP method.",
          "description_fr": "La ressource a définitivement bougé, méthode HTTP préservée.",
          "rfc": "RFC 7538", "usage": "Permanent redirect preserving POST method."},
    # 4xx Client Errors
    400: {"name_en": "Bad Request", "name_fr": "Mauvaise requête", "category": "client_error",
          "description_en": "The server cannot process the request due to client error.",
          "description_fr": "Le serveur ne peut pas traiter la requête à cause d'une erreur client.",
          "rfc": "RFC 7231", "usage": "Generic client error, invalid syntax."},
    401: {"name_en": "Unauthorized", "name_fr": "Non autorisé", "category": "client_error",
          "description_en": "The client must authenticate itself to get the requested response.",
          "description_fr": "Le client doit s'authentifier pour obtenir la réponse.",
          "rfc": "RFC 7235", "usage": "Authentication required."},
    402: {"name_en": "Payment Required", "name_fr": "Paiement requis", "category": "client_error",
          "description_en": "Payment is required. Used in x402 protocol for micropayments.",
          "description_fr": "Un paiement est requis. Utilisé dans le protocole x402.",
          "rfc": "RFC 7231", "usage": "x402 protocol, micropayments, reserved for future use."},
    403: {"name_en": "Forbidden", "name_fr": "Interdit", "category": "client_error",
          "description_en": "The client does not have access rights to the content.",
          "description_fr": "Le client n'a pas les droits d'accès au contenu.",
          "rfc": "RFC 7231", "usage": "Authorization failure, identity known but refused."},
    404: {"name_en": "Not Found", "name_fr": "Non trouvé", "category": "client_error",
          "description_en": "The server cannot find the requested resource.",
          "description_fr": "Le serveur ne trouve pas la ressource demandée.",
          "rfc": "RFC 7231", "usage": "Most common error on the web."},
    405: {"name_en": "Method Not Allowed", "name_fr": "Méthode non autorisée", "category": "client_error",
          "description_en": "The HTTP method is not supported for the resource.",
          "description_fr": "La méthode HTTP n'est pas supportée pour cette ressource.",
          "rfc": "RFC 7231", "usage": "Used when GET-only endpoint receives POST."},
    406: {"name_en": "Not Acceptable", "name_fr": "Non acceptable", "category": "client_error",
          "description_en": "No content conforming to the Accept headers was found.",
          "description_fr": "Aucun contenu conforme aux en-têtes Accept n'a été trouvé.",
          "rfc": "RFC 7231", "usage": "Content negotiation failure."},
    407: {"name_en": "Proxy Authentication Required", "name_fr": "Authentification proxy requise", "category": "client_error",
          "description_en": "Authentication with a proxy is required.",
          "description_fr": "Une authentification avec le proxy est requise.",
          "rfc": "RFC 7235", "usage": "Similar to 401 but for proxy servers."},
    408: {"name_en": "Request Timeout", "name_fr": "Délai de requête dépassé", "category": "client_error",
          "description_en": "The server timed out waiting for the request.",
          "description_fr": "Le serveur a expiré en attendant la requête.",
          "rfc": "RFC 7231", "usage": "Connection timeout from client side."},
    409: {"name_en": "Conflict", "name_fr": "Conflit", "category": "client_error",
          "description_en": "The request conflicts with the current state of the server.",
          "description_fr": "La requête entre en conflit avec l'état actuel du serveur.",
          "rfc": "RFC 7231", "usage": "Edit conflict in version control systems."},
    410: {"name_en": "Gone", "name_fr": "Disparu", "category": "client_error",
          "description_en": "The resource is no longer available and will not be available again.",
          "description_fr": "La ressource n'est plus disponible et ne le sera plus.",
          "rfc": "RFC 7231", "usage": "Permanent removal, unlike 404."},
    411: {"name_en": "Length Required", "name_fr": "Longueur requise", "category": "client_error",
          "description_en": "Content-Length header field is required.",
          "description_fr": "L'en-tête Content-Length est requis.",
          "rfc": "RFC 7231", "usage": "Server requires Content-Length header."},
    412: {"name_en": "Precondition Failed", "name_fr": "Précondition échouée", "category": "client_error",
          "description_en": "The server does not meet one of the preconditions in the request headers.",
          "description_fr": "Le serveur ne satisfait pas une des préconditions.",
          "rfc": "RFC 7232", "usage": "Conditional requests with If-Match."},
    413: {"name_en": "Content Too Large", "name_fr": "Contenu trop volumineux", "category": "client_error",
          "description_en": "The request body is larger than the server is willing to process.",
          "description_fr": "Le corps de la requête est trop volumineux.",
          "rfc": "RFC 7231", "usage": "File upload size limit exceeded."},
    414: {"name_en": "URI Too Long", "name_fr": "URI trop longue", "category": "client_error",
          "description_en": "The URI requested is longer than the server is willing to interpret.",
          "description_fr": "L'URI est trop longue pour être interprétée.",
          "rfc": "RFC 7231", "usage": "URL length exceeds server limits."},
    415: {"name_en": "Unsupported Media Type", "name_fr": "Type de média non supporté", "category": "client_error",
          "description_en": "The media format is not supported by the server.",
          "description_fr": "Le format de média n'est pas supporté.",
          "rfc": "RFC 7231", "usage": "Wrong Content-Type header."},
    416: {"name_en": "Range Not Satisfiable", "name_fr": "Plage non satisfaisable", "category": "client_error",
          "description_en": "The range specified by Range header cannot be fulfilled.",
          "description_fr": "La plage spécifiée ne peut pas être satisfaite.",
          "rfc": "RFC 7233", "usage": "Used with partial content requests."},
    417: {"name_en": "Expectation Failed", "name_fr": "Attente échouée", "category": "client_error",
          "description_en": "The expectation indicated in the Expect header cannot be met.",
          "description_fr": "L'attente indiquée dans l'en-tête Expect ne peut être satisfaite.",
          "rfc": "RFC 7231", "usage": "Server cannot meet Expect: 100-continue."},
    418: {"name_en": "I'm a Teapot", "name_fr": "Je suis une théière", "category": "client_error",
          "description_en": "The server refuses to brew coffee because it is a teapot.",
          "description_fr": "Le serveur refuse de faire du café car il est une théière.",
          "rfc": "RFC 2324 (HTCPCP)", "usage": "April Fool's joke, used for Easter eggs."},
    421: {"name_en": "Misdirected Request", "name_fr": "Requête mal dirigée", "category": "client_error",
          "description_en": "The request was directed at a server that is not able to produce a response.",
          "description_fr": "La requête a été dirigée vers un serveur qui ne peut pas répondre.",
          "rfc": "RFC 7540", "usage": "HTTP/2 multiplexing error."},
    422: {"name_en": "Unprocessable Content", "name_fr": "Contenu non traitable", "category": "client_error",
          "description_en": "The request was well-formed but was unable to be processed.",
          "description_fr": "La requête est bien formée mais ne peut pas être traitée.",
          "rfc": "RFC 4918 (WebDAV)", "usage": "Validation error, commonly used in REST APIs."},
    423: {"name_en": "Locked", "name_fr": "Verrouillé", "category": "client_error",
          "description_en": "The resource being accessed is locked.",
          "description_fr": "La ressource est verrouillée.",
          "rfc": "RFC 4918 (WebDAV)", "usage": "WebDAV file locking."},
    424: {"name_en": "Failed Dependency", "name_fr": "Dépendance échouée", "category": "client_error",
          "description_en": "The request failed because it depended on another request that failed.",
          "description_fr": "La requête a échoué car elle dépendait d'une autre requête.",
          "rfc": "RFC 4918 (WebDAV)", "usage": "WebDAV batch operations."},
    425: {"name_en": "Too Early", "name_fr": "Trop tôt", "category": "client_error",
          "description_en": "The server is unwilling to process a request that might be replayed.",
          "description_fr": "Le serveur refuse de traiter une requête qui pourrait être rejouée.",
          "rfc": "RFC 8470", "usage": "TLS 1.3 early data (0-RTT)."},
    426: {"name_en": "Upgrade Required", "name_fr": "Mise à niveau requise", "category": "client_error",
          "description_en": "The client should switch to a different protocol.",
          "description_fr": "Le client doit passer à un protocole différent.",
          "rfc": "RFC 7231", "usage": "Requires TLS or WebSocket upgrade."},
    428: {"name_en": "Precondition Required", "name_fr": "Précondition requise", "category": "client_error",
          "description_en": "The origin server requires the request to be conditional.",
          "description_fr": "Le serveur exige que la requête soit conditionnelle.",
          "rfc": "RFC 6585", "usage": "Prevents lost-update problems in REST APIs."},
    429: {"name_en": "Too Many Requests", "name_fr": "Trop de requêtes", "category": "client_error",
          "description_en": "The user has sent too many requests in a given time period.",
          "description_fr": "L'utilisateur a envoyé trop de requêtes dans un temps donné.",
          "rfc": "RFC 6585", "usage": "Rate limiting."},
    431: {"name_en": "Request Header Fields Too Large", "name_fr": "Champs d'en-tête trop grands", "category": "client_error",
          "description_en": "The server is unwilling to process the request because its header fields are too large.",
          "description_fr": "Les champs d'en-tête de la requête sont trop grands.",
          "rfc": "RFC 6585", "usage": "HTTP headers exceeding server limits."},
    451: {"name_en": "Unavailable For Legal Reasons", "name_fr": "Indisponible pour raisons légales", "category": "client_error",
          "description_en": "The server is denying access to the resource as a consequence of a legal demand.",
          "description_fr": "L'accès est refusé pour des raisons légales.",
          "rfc": "RFC 7725", "usage": "Content blocked by government or DMCA."},
    # 5xx Server Errors
    500: {"name_en": "Internal Server Error", "name_fr": "Erreur interne du serveur", "category": "server_error",
          "description_en": "The server has encountered a situation it does not know how to handle.",
          "description_fr": "Le serveur a rencontré une situation qu'il ne sait pas gérer.",
          "rfc": "RFC 7231", "usage": "Generic server error."},
    501: {"name_en": "Not Implemented", "name_fr": "Non implémenté", "category": "server_error",
          "description_en": "The request method is not supported by the server.",
          "description_fr": "La méthode de requête n'est pas supportée par le serveur.",
          "rfc": "RFC 7231", "usage": "Server does not support the HTTP method."},
    502: {"name_en": "Bad Gateway", "name_fr": "Mauvaise passerelle", "category": "server_error",
          "description_en": "The server received an invalid response from an upstream server.",
          "description_fr": "Le serveur a reçu une réponse invalide d'un serveur en amont.",
          "rfc": "RFC 7231", "usage": "Proxy/load balancer upstream error."},
    503: {"name_en": "Service Unavailable", "name_fr": "Service indisponible", "category": "server_error",
          "description_en": "The server is not ready to handle the request.",
          "description_fr": "Le serveur n'est pas prêt à traiter la requête.",
          "rfc": "RFC 7231", "usage": "Server overloaded or in maintenance."},
    504: {"name_en": "Gateway Timeout", "name_fr": "Délai de passerelle dépassé", "category": "server_error",
          "description_en": "The server acting as a gateway did not get a response in time.",
          "description_fr": "La passerelle n'a pas reçu de réponse à temps.",
          "rfc": "RFC 7231", "usage": "Upstream server timeout."},
    505: {"name_en": "HTTP Version Not Supported", "name_fr": "Version HTTP non supportée", "category": "server_error",
          "description_en": "The HTTP version used in the request is not supported by the server.",
          "description_fr": "La version HTTP utilisée n'est pas supportée.",
          "rfc": "RFC 7231", "usage": "Old HTTP version not supported."},
    506: {"name_en": "Variant Also Negotiates", "name_fr": "Variante négocie aussi", "category": "server_error",
          "description_en": "The server has an internal configuration error.",
          "description_fr": "Le serveur a une erreur de configuration interne.",
          "rfc": "RFC 2295", "usage": "Transparent content negotiation error."},
    507: {"name_en": "Insufficient Storage", "name_fr": "Stockage insuffisant", "category": "server_error",
          "description_en": "The server is unable to store the representation needed to complete the request.",
          "description_fr": "Le serveur ne peut pas stocker les données nécessaires.",
          "rfc": "RFC 4918 (WebDAV)", "usage": "WebDAV storage limit exceeded."},
    508: {"name_en": "Loop Detected", "name_fr": "Boucle détectée", "category": "server_error",
          "description_en": "The server detected an infinite loop while processing the request.",
          "description_fr": "Le serveur a détecté une boucle infinie.",
          "rfc": "RFC 5842", "usage": "WebDAV infinite loop detection."},
    510: {"name_en": "Not Extended", "name_fr": "Non étendu", "category": "server_error",
          "description_en": "Further extensions to the request are required for the server to fulfill it.",
          "description_fr": "Des extensions supplémentaires sont requises.",
          "rfc": "RFC 2774", "usage": "HTTP extensions required."},
    511: {"name_en": "Network Authentication Required", "name_fr": "Authentification réseau requise", "category": "server_error",
          "description_en": "The client needs to authenticate to gain network access.",
          "description_fr": "Le client doit s'authentifier pour accéder au réseau.",
          "rfc": "RFC 6585", "usage": "Captive portals (hotel/airport WiFi)."},
}

PAID_PATHS_STARTS = ("/code/", "/search")


def _make_402(host: str, endpoint: str = "/code/404") -> JSONResponse:
    return JSONResponse(
        status_code=402,
        content={"x402Version": 1, "error": "Payment required", "accepts": [{
            "scheme": "exact", "network": NETWORK, "maxAmountRequired": PRICE_ATOMIC,
            "resource": f"https://{host}{endpoint}",
            "description": "HTTP status code information (EN+FR, RFC, usage)",
            "mimeType": "application/json", "payTo": PAY_TO, "maxTimeoutSeconds": 300,
            "asset": ASSET_ADDRESS, "extra": {"name": "USDC", "version": "2"},
        }]},
        headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "no-store",
                 "Access-Control-Expose-Headers": "X-PAYMENT-RESPONSE"},
    )


@app.middleware("http")
async def x402_middleware(request: Request, call_next):
    path = request.url.path
    is_paid = (path.startswith("/code/") or path == "/search" or path == "/check") and \
              request.method in ("GET", "POST")
    if is_paid:
        if not (request.headers.get("X-PAYMENT") or request.headers.get("x-payment")):
            return _make_402(request.headers.get("host", "x402-http-status.suretat.com"))
    return await call_next(request)


class CheckRequest(BaseModel):
    url: str
    method: Optional[str] = "HEAD"


@app.get("/")
def root():
    return {"service": "x402 HTTP Status", "price": f"{int(PRICE_ATOMIC)/1_000_000} USDC/appel",
            "codes_count": len(HTTP_CODES), "docs": "/docs"}


@app.get("/code/{status_code}")
def get_code(status_code: int, request: Request):
    stats["total_paid"] += 1
    stats["revenue_usdc"] += int(PRICE_ATOMIC) / 1_000_000

    if status_code not in HTTP_CODES:
        return JSONResponse(status_code=404, content={"error": f"Unknown HTTP status code: {status_code}"})

    info = HTTP_CODES[status_code]
    return {"code": status_code, **info}


@app.get("/search")
def search(q: str = Query(..., description="Search by name or description"), request: Request = None):
    stats["total_paid"] += 1
    stats["revenue_usdc"] += int(PRICE_ATOMIC) / 1_000_000

    q_lower = q.lower().strip()
    results = []
    for code, info in HTTP_CODES.items():
        if (q_lower in info["name_en"].lower() or q_lower in info["name_fr"].lower()
                or q_lower in info["description_en"].lower() or q_lower in str(code)):
            results.append({"code": code, **info})

    return {"query": q, "count": len(results), "results": results}


@app.post("/check")
async def check_url(req: CheckRequest):
    stats["total_paid"] += 1
    stats["revenue_usdc"] += int(PRICE_ATOMIC) / 1_000_000

    method = (req.method or "HEAD").upper()
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=10.0) as client:
            response = await client.request(method, req.url)

        code = response.status_code
        info = HTTP_CODES.get(code, {})
        return {
            "url": str(response.url),
            "status_code": code,
            "name_en": info.get("name_en", "Unknown"),
            "name_fr": info.get("name_fr", "Inconnu"),
            "category": info.get("category", "unknown"),
            "description_en": info.get("description_en", ""),
            "redirect_count": len(response.history),
        }
    except httpx.TimeoutException:
        return JSONResponse(status_code=504, content={"error": "Request timed out"})
    except httpx.RequestError as e:
        return JSONResponse(status_code=502, content={"error": f"Request failed: {str(e)}"})


@app.get("/.well-known/x402.json")
async def x402_well_known(request: Request):
    host = request.headers.get("host", "x402-http-status.suretat.com")
    return {"x402Version": 1, "accepts": [{"scheme": "exact", "network": NETWORK,
        "maxAmountRequired": PRICE_ATOMIC, "resource": f"https://{host}/code/404",
        "description": "HTTP status code information (EN+FR, RFC, usage)",
        "mimeType": "application/json", "payTo": PAY_TO, "maxTimeoutSeconds": 300,
        "asset": ASSET_ADDRESS, "extra": {"name": "USDC", "version": "2"}}]}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/stats")
def get_stats():
    return {**stats, "uptime_seconds": int(time.time() - stats["start_time"])}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=3112, proxy_headers=True, forwarded_allow_ips="*")
