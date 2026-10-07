"""Provider-neutral cloud translation client. Never logs or returns API keys."""
import html
import json
import urllib.error
import urllib.parse
import urllib.request


SERVICE_NAMES = {1: "azure", 2: "google", 3: "deepl"}


class CloudTranslationError(RuntimeError):
    def __init__(self, code):
        self.code = str(code)
        super().__init__(self.code)


def is_session_blocking_error(error):
    """True when retrying with the same credentials cannot help this session.

    HTTP responses prove that the provider was reached.  They cover exhausted
    quota, rejected credentials, disabled APIs and other account-side errors.
    A fresh worker may try again, so changing a key or starting Translation
    Mode on another day does not require deleting any local state.
    """
    code = str(getattr(error, "code", str(error)))
    if not code.startswith("HTTP_"):
        return False
    try:
        status = int(code.split("_", 1)[1])
    except (IndexError, ValueError):
        return False
    # Retryable transport/service conditions retain the ordinary short circuit
    # breaker.  Other 4xx replies indicate a key, permission, request/account,
    # or hard-quota problem that will not improve by retrying every message.
    return 400 <= status < 500 and status not in (408, 425, 429)


def _post_json(url, headers, payload, timeout, opener):
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with opener(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        # Never include error.url or the response body: Google places its key
        # in the query string and providers can echo request information.
        raise CloudTranslationError("HTTP_%s" % error.code) from None
    except urllib.error.URLError:
        raise CloudTranslationError("NETWORK_UNAVAILABLE") from None
    except (ValueError, UnicodeError):
        raise CloudTranslationError("INVALID_JSON_RESPONSE") from None


def translate_azure_many(texts, api_key, region="global", timeout=1.5, opener=urllib.request.urlopen):
    url = "https://api.cognitive.microsofttranslator.com/translate?api-version=3.0&from=en&to=zh-Hant"
    headers = {
        "Content-Type": "application/json; charset=UTF-8",
        "Ocp-Apim-Subscription-Key": api_key,
    }
    if region and region.lower() != "global":
        headers["Ocp-Apim-Subscription-Region"] = region
    data = _post_json(url, headers, [{"Text": text} for text in texts], timeout, opener)
    try:
        results = [str(item["translations"][0]["text"]).strip() for item in data]
        if len(results) != len(texts):
            raise CloudTranslationError("AZURE_RESPONSE_COUNT")
        return results
    except (KeyError, IndexError, TypeError):
        raise CloudTranslationError("AZURE_RESPONSE_SHAPE") from None


def translate_google_many(texts, api_key, timeout=1.5, opener=urllib.request.urlopen):
    query = urllib.parse.urlencode({"key": api_key})
    url = "https://translation.googleapis.com/language/translate/v2?" + query
    payload = {"q": list(texts), "source": "en", "target": "zh-TW", "format": "text"}
    data = _post_json(url, {"Content-Type": "application/json; charset=UTF-8"}, payload, timeout, opener)
    try:
        results = [html.unescape(str(item["translatedText"])).strip()
                   for item in data["data"]["translations"]]
        if len(results) != len(texts):
            raise CloudTranslationError("GOOGLE_RESPONSE_COUNT")
        return results
    except (KeyError, IndexError, TypeError):
        raise CloudTranslationError("GOOGLE_RESPONSE_SHAPE") from None


def translate_deepl_many(texts, api_key, timeout=1.5, opener=urllib.request.urlopen):
    host = "api-free.deepl.com" if api_key.strip().endswith(":fx") else "api.deepl.com"
    url = "https://%s/v2/translate" % host
    headers = {
        "Authorization": "DeepL-Auth-Key " + api_key,
        "Content-Type": "application/json; charset=UTF-8",
    }
    payload = {"text": list(texts), "source_lang": "EN", "target_lang": "ZH-HANT"}
    data = _post_json(url, headers, payload, timeout, opener)
    try:
        results = [str(item["text"]).strip() for item in data["translations"]]
        if len(results) != len(texts):
            raise CloudTranslationError("DEEPL_RESPONSE_COUNT")
        return results
    except (KeyError, IndexError, TypeError):
        raise CloudTranslationError("DEEPL_RESPONSE_SHAPE") from None


def translate_many(service, texts, api_key, azure_region="global", timeout=1.5,
                   opener=urllib.request.urlopen):
    texts = [str(text) for text in texts]
    if not texts:
        return []
    results = []
    # Azure accepts at most 25 array elements. Use that conservative bound for
    # every provider so switching services never changes reconstruction rules.
    for start in range(0, len(texts), 25):
        batch = texts[start:start + 25]
        if service == 1:
            translated = translate_azure_many(batch, api_key, azure_region, timeout, opener)
        elif service == 2:
            translated = translate_google_many(batch, api_key, timeout, opener)
        elif service == 3:
            translated = translate_deepl_many(batch, api_key, timeout, opener)
        else:
            raise CloudTranslationError("SERVICE_DISABLED_OR_UNKNOWN")
        results.extend(translated)
    return results


def translate(service, text, api_key, azure_region="global", timeout=1.5,
              opener=urllib.request.urlopen):
    return translate_many(service, [text], api_key, azure_region, timeout, opener)[0]
