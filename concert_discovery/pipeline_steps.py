"""Provider failures must not prevent independent enrichment stages running."""
import requests

def attempt(result,warnings,name,work):
    try:
        result.update(work())
    except (requests.RequestException,RuntimeError,ValueError) as error:
        result.setdefault('enrichment_failures',[]).append(name)
        warnings.append(name+' unavailable; saved values retained ('+type(error).__name__+')')
