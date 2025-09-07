
import pathlib, re
WIKI=pathlib.Path("docs/wiki"); MB=WIKI/"memory_bank"
PAGES={
  "Storage": WIKI/"06-Storage-Rook-Ceph.md",
  "Networking": WIKI/"07-Networking-and-Ingress.md",
  "GitOps/IaC": WIKI/"05-GitOps-and-IaC.md",
  "Security/Certs": WIKI/"08-Security-and-Certificates.md",
  "Apps": WIKI/"09-Apps.md",
}
def classify(t):
  t=t.lower()
  if any(k in t for k in ["ceph","rbd","cephfs","mds","erasure","storageclass"]): return "Storage"
  if any(k in t for k in ["metallb","traefik","ingress","dns","pihole"]): return "Networking"
  if any(k in t for k in ["argocd","helm","ansible","iac","gitops","cleanup","wipe"]): return "GitOps/IaC"
  if any(k in t for k in ["cert","tls","ca","acme","keycloak","oauth2-proxy"]): return "Security/Certs"
  if any(k in t for k in ["plex","n8n","openwebui","bedrock"]): return "Apps"
  return None
def inject(page, items):
  md=page.read_text(encoding="utf-8") if page.exists() else f"# {page.stem}\n\n"
  md=re.sub(r"\n## From the Memory Bank[\s\S]*$", "", md, flags=re.M|re.S)
  md+="\n\n## From the Memory Bank\n\n"
  for title, rel in items: md+=f"- [{title}]({rel})\n"
  page.write_text(md, encoding="utf-8")
  print("Updated", page)
bucket={k:[] for k in PAGES}
if MB.exists():
  for p in sorted(MB.glob("*.md")):
    txt=p.read_text(encoding="utf-8", errors="ignore"); tag=classify(txt)
    if not tag: continue
    title=txt.splitlines()[0].strip("# ").strip() if txt.startswith("#") else p.stem.replace("-", " ")
    bucket[tag].append((title, f"memory_bank/{p.name}"))
for k, items in bucket.items():
  if items: inject(PAGES[k], items)
