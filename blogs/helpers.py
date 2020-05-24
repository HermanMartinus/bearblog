import requests
import json
from markdown import Markdown
from io import StringIO

def get_root(extracted, subdomain):
    if extracted.suffix:
        return "https://{}.{}.{}".format(subdomain, extracted.domain, extracted.suffix)
    else:
        return "http://{}.{}:{}".format(subdomain, extracted.domain, '8000')

def get_base_root(extracted):
    if extracted.suffix:
        return "https://{}.{}".format(extracted.domain, extracted.suffix)
    else:
        return "http://{}:{}".format(extracted.domain, '8000')

def set_dns_record(record_type, name):
    url = "https://api.cloudflare.com/client/v4/zones/2076fad18ca9cebee92de5a65942f9fe/dns_records"

    payload = {
        "type": record_type,
        "name": name,
        "content": "intense-shallot-9foagelzs54op9wrom8ybsbn.herokudns.com",
        "ttl": "120",
        "proxied": "true"
    }
    headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer SWCl5sHFnx8SAqowIM0ZrpntrS9aeaGfB40Di1gv',
    'Content-Type': 'text/plain',
    'Cookie': '__cfduid=dc242bd25444397766d1abf29dd6672ed1590168756'
    }

    response = requests.request("POST", url, headers=headers, data = json.dumps(payload))

    print(response.text.encode('utf8'))

def unmark_element(element, stream=None):
    if stream is None:
        stream = StringIO()
    if element.text:
        stream.write(element.text)
    for sub in element:
        unmark_element(sub, stream)
    if element.tail:
        stream.write(element.tail)
    return stream.getvalue()


# patching Markdown
Markdown.output_formats["plain"] = unmark_element
__md = Markdown(output_format="plain")
__md.stripTopLevelTags = False


def unmark(text):
    return __md.convert(text)