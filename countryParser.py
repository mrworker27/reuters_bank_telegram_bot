import json
import pycurl
from io import BytesIO

template = "http://api.worldbank.org/v2/country/%s/indicator/%s?format=json"
mapping = {}
def parseMappings():
    global mapping
    if len(mapping) == 0:
        print("parse mappings")
        inp = open("countryMappings.json", "r")
        mapping = json.loads(inp.read())
        inp.close()
    
    return mapping

def getRawHTML(url):
	b_obj = BytesIO()
	crl = pycurl.Curl()
	crl.setopt(crl.URL, url)
	crl.setopt(pycurl.TIMEOUT, 30)
	crl.setopt(crl.WRITEDATA, b_obj)
	crl.perform()
	crl.close()
	get_body = b_obj.getvalue()
	return get_body.decode("utf8")

def getData(country, command):
    code = parseMappings()[country]
    raw = getRawHTML(template % (code, command))
    parsed = json.loads(raw)
    res = {}
    for x in parsed[1]:
        if x["value"] is not None:
            res[x["date"]] = x["value"]
    return res
def getGDP(countryName):
    command = "NY.GDP.MKTP.CD"
    return getData(countryName, command)

res = getGDP("China")
print(res)
