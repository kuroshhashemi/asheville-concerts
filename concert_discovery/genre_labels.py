"""Display labels for JamBase genres; preserve raw source metadata."""
import re

def genre_label(value):
    key=re.sub(r'\s+',' ',value.replace('-',' ').strip()).casefold()
    aliases={'blues rock':'Blues','country music':'Country','hip hop rap':'Hip-Hop & Rap','indie rock':'Indie','rhythm and blues soul':'R&B','rythem and blues soul':'R&B','edm':'EDM'}
    return aliases.get(key,key.title())

def genre_labels(value):
    return list(dict.fromkeys(genre_label(g) for g in (value or '').split(',') if g.strip()))
