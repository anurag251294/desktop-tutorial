# E2E harness, first cell: an in-memory SharePoint served through a fake `requests` module.
#
# Everything else in the run is real: Spark, Delta, OneLake (notebookutils.fs) and the Fabric
# notebook runtime. Only the calls to login.microsoftonline.com and graph.microsoft.com are
# answered here, shaped like Graph's real responses: the delta feed carries parentReference.id
# but not parentReference.path, a plain item GET carries the percent-encoded path, the same
# item can repeat in one feed, a renamed folder comes back without its children, and an
# expired delta link answers 410 with a Location to restart from.
import sys, types, urllib.parse

GRAPH = "https://graph.microsoft.com/v1.0"
HOST = "contoso.sharepoint.com"
PAGE = 3


class FakeHTTPError(Exception):
    pass


class FakeResp:
    def __init__(self, status=200, body=None, content=b"", headers=None):
        self.status_code, self._body, self.content = status, body, content
        self.headers = headers or {}

    def json(self):
        return self._body

    def iter_content(self, chunk_size=1):
        for i in range(0, len(self.content), chunk_size):
            yield self.content[i:i + chunk_size]

    def raise_for_status(self):
        if self.status_code >= 400:
            raise FakeHTTPError(f"{self.status_code} Client/Server Error (fake Graph)")

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class Drive:
    def __init__(self, drive_id, name):
        self.id, self.name = drive_id, name
        self.items = {"root": {"name": "root", "parent": None, "folder": True, "content": None}}
        self.seq, self.n = 0, 0
        self.changed, self.deleted = {}, {}
        self.fresh_order = None     # optional explicit order (with repeats) for a fresh enumeration
        self.expired = set()        # delta tokens that answer 410

    def _new(self, name, parent, folder, content):
        self.n += 1
        iid = f"{self.id}-i{self.n}"
        self.items[iid] = {"name": name, "parent": parent, "folder": folder, "content": content}
        self._touch(iid)
        return iid

    def _touch(self, iid):
        self.seq += 1
        self.changed[iid] = self.seq

    def mkdir(self, name, parent="root"):
        return self._new(name, parent, True, None)

    def put(self, name, parent, content):
        return self._new(name, parent, False, content)

    def modify(self, iid, content):
        self.items[iid]["content"] = content
        self._touch(iid)

    def rename(self, iid, name):
        self.items[iid]["name"] = name
        self._touch(iid)            # Graph reports only the folder, not its children

    def move(self, iid, parent):
        self.items[iid]["parent"] = parent
        self._touch(iid)

    def delete(self, iid):
        del self.items[iid]
        self.changed.pop(iid, None)
        self.seq += 1
        self.deleted[iid] = self.seq

    def path_of(self, iid):
        parts = []
        while iid != "root":
            parts.append(self.items[iid]["name"])
            iid = self.items[iid]["parent"]
        return "/".join(reversed(parts))

    def files(self):
        return {self.path_of(i): v["content"] for i, v in self.items.items()
                if i != "root" and not v["folder"]}

    def all_paths(self):
        return {self.path_of(i) for i in self.items if i != "root"}

    def item_json(self, iid, with_path=False):
        if iid == "root":
            return {"id": "root", "name": "root", "root": {}, "folder": {"childCount": 0},
                    "parentReference": {"driveId": self.id}}
        v = self.items[iid]
        d = {"id": iid, "name": v["name"],
             "parentReference": {"id": v["parent"], "driveId": self.id},
             "webUrl": f"https://{HOST}/sites/E2E/{urllib.parse.quote(self.path_of(iid))}",
             "lastModifiedDateTime": "2026-11-17T00:00:00Z", "createdDateTime": "2026-11-01T00:00:00Z"}
        if v["folder"]:
            d["folder"] = {"childCount": sum(1 for x in self.items.values() if x["parent"] == iid)}
            d["size"] = 0
        else:
            d["file"] = {"mimeType": "application/octet-stream"}
            d["size"] = len(v["content"])
        if with_path:
            pp = self.path_of(v["parent"]) if v["parent"] != "root" else ""
            d["parentReference"]["path"] = "/drive/root:" + (urllib.parse.quote("/" + pp) if pp else "")
        return d

    def delta_entries(self, token):
        if token is None:
            # The explicit order (with its repeats) first, then anything created since.
            order = list(self.fresh_order or [])
            order += [i for i in self.items if i not in order]
            ids = ["root"] + [i for i in order if i in self.items and i != "root"]
            return [self.item_json(i) for i in ids]
        events = [(s, i, False) for i, s in self.changed.items() if s > token and i in self.items]
        events += [(s, i, True) for i, s in self.deleted.items() if s > token]
        return [({"id": i, "deleted": {"state": "deleted"}} if dead else self.item_json(i))
                for s, i, dead in sorted(events)]


class FakeGraph:
    def __init__(self):
        self.drives = {}
        self.faults = []            # dicts: match, status, headers, times
        self.calls = []
        self.token_posts = 0

    def add_drive(self, drive):
        self.drives[drive.id] = drive
        return drive

    def fault(self, match, status, times=1, headers=None):
        self.faults.append({"match": match, "status": status, "times": times, "headers": headers or {}})

    def clear_faults(self):
        self.faults = []

    def post(self, url, data=None, timeout=None, **kw):
        self.calls.append(("POST", url))
        if url.startswith("https://login.microsoftonline.com/"):
            self.token_posts += 1
            return FakeResp(200, {"access_token": f"tok-{self.token_posts}", "expires_in": 3599,
                                  "token_type": "Bearer"})
        return FakeResp(404, {"error": {"code": "itemNotFound"}})

    def get(self, url, headers=None, timeout=None, stream=False, **kw):
        self.calls.append(("GET", url))
        if not (headers or {}).get("Authorization", "").startswith("Bearer tok-"):
            return FakeResp(401, {"error": {"code": "InvalidAuthenticationToken"}})
        for f in self.faults:
            if f["times"] > 0 and f["match"] in url:
                f["times"] -= 1
                return FakeResp(f["status"], {"error": {"code": "injected"}}, headers=dict(f["headers"]))
        u = urllib.parse.urlparse(url)
        q = urllib.parse.parse_qs(u.query)
        path = urllib.parse.unquote(u.path)
        if path.startswith(f"/v1.0/sites/{HOST}:"):
            return FakeResp(200, {"id": "site-1", "webUrl": f"https://{HOST}/sites/E2E"})
        if path == "/v1.0/sites/site-1/drives":
            ds = [{"id": d.id, "name": d.name} for d in self.drives.values()]
            if "page" not in q:     # the library list is paged too
                return FakeResp(200, {"value": [{"id": "drive-assets", "name": "Site Assets"}],
                                      "@odata.nextLink": f"{GRAPH}/sites/site-1/drives?page=2"})
            return FakeResp(200, {"value": ds})
        if path.endswith("/root/delta"):
            drive = self.drives[path.split("/drives/")[1].split("/")[0]]
            token = int(q["token"][0]) if "token" in q else None
            if token is not None and token in drive.expired:
                return FakeResp(410, {"error": {"code": "resyncRequired"}},
                                headers={"Location": f"{GRAPH}/drives/{drive.id}/root/delta"})
            entries = drive.delta_entries(token)
            skip = int(q.get("skip", ["0"])[0])
            page = entries[skip:skip + PAGE]
            base = f"{GRAPH}/drives/{drive.id}/root/delta?" + (f"token={token}&" if token is not None else "")
            if skip + PAGE < len(entries):
                return FakeResp(200, {"value": page, "@odata.nextLink": f"{base}skip={skip + PAGE}"})
            return FakeResp(200, {"value": page,
                                  "@odata.deltaLink": f"{GRAPH}/drives/{drive.id}/root/delta?token={drive.seq}"})
        if "/items/" in path:
            drive = self.drives[path.split("/drives/")[1].split("/")[0]]
            rest = path.split("/items/")[1]
            iid, _, tail = rest.partition("/")
            if iid not in drive.items:
                return FakeResp(404, {"error": {"code": "itemNotFound"}})
            if tail == "content":
                return FakeResp(200, content=drive.items[iid]["content"])
            return FakeResp(200, drive.item_json(iid, with_path=True))
        return FakeResp(404, {"error": {"code": "notFound", "message": url}})


FAKE = FakeGraph()
_requests = types.ModuleType("requests")
_requests.get, _requests.post, _requests.HTTPError = FAKE.get, FAKE.post, FakeHTTPError
sys.modules["requests"] = _requests
print("fake Graph installed")
