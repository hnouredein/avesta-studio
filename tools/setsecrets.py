import json, base64, os, urllib.request
import nacl.public, nacl.encoding

repo = "hnouredein/avesta-studio"
tok = os.environ["GHTOKEN"]
folder_id = "1T2eeUbyRVYZyP-QP_oCEMS3rNoMzsCmu"

def gh(path, method="GET", data=None):
    req = urllib.request.Request(
        "https://api.github.com" + path, method=method,
        headers={"Authorization": "Bearer " + tok,
                 "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28"},
        data=json.dumps(data).encode() if data is not None else None)
    resp = urllib.request.urlopen(req)
    body = resp.read()
    return resp.status, (json.loads(body) if body else {})

status, pk = gh("/repos/" + repo + "/actions/secrets/public-key")
pub = nacl.public.PublicKey(pk["key"], nacl.encoding.Base64Encoder)
box = nacl.public.SealedBox(pub)

def seal(v):
    return base64.b64encode(box.encrypt(v.encode())).decode()

sa = open(os.path.expanduser("~/sa-key.json")).read()
s1, _ = gh("/repos/" + repo + "/actions/secrets/GDRIVE_SA_JSON", "PUT",
           {"encrypted_value": seal(sa), "key_id": pk["key_id"]})
s2, _ = gh("/repos/" + repo + "/actions/secrets/DRIVE_FOLDER_ID", "PUT",
           {"encrypted_value": seal(folder_id), "key_id": pk["key_id"]})
print("SECRETS_SET_OK", s1, s2)
