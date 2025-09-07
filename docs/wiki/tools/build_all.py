#!/usr/bin/env python3
"""
One-shot wiki generator (self-contained):
- Builds ALL wiki pages from README + manifests + memory_bank + local images.
- Writes ONLY under docs/wiki/** (no external links/assets).
- Safe to run repeatedly; overwrites generated pages in-place.

Usage:
  python docs/wiki/tools/build_all.py
"""

import pathlib, re, datetime

ROOT = pathlib.Path(".")
WIKI = ROOT / "docs/wiki"
IMAGES = WIKI / "images"
MB = WIKI / "memory_bank"

def ensure_dirs():
    WIKI.mkdir(parents=True, exist_ok=True)
    IMAGES.mkdir(parents=True, exist_ok=True)
    MB.mkdir(parents=True, exist_ok=True)

def read_text(p):
    try:
        return pathlib.Path(p).read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""

def write_text(path, text):
    pathlib.Path(path).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(path).write_text(text, encoding="utf-8")

def now_utc():
    return datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

# ---------- repo scanners ----------
def list_images(keys=("arch","diagram","rack","topology","layout","network","ingress","traefik","ceph","storage","grafana","pihole","openwebui","plex")):
    out=[]
    if IMAGES.exists():
        for p in sorted(IMAGES.glob("*")):
            if p.is_dir(): continue
            name=p.name.lower()
            if any(k in name for k in keys) and p.suffix.lower() in (".png",".jpg",".jpeg",".svg",".webp"):
                out.append(f"images/{p.name}")
    return out

def grep_yaml(pattern, limit=200):
    matches=[]
    for p in ROOT.rglob("*.y*ml"):
        # skip workflow files
        if ".github/workflows" in str(p): continue
        t = read_text(p)
        if pattern in t:
            matches.append((str(p), t))
            if len(matches)>=limit: break
    return matches

def find_storageclasses():
    names=set()
    for _, t in grep_yaml("kind: StorageClass"):
        names.update(re.findall(r"name:\s*([A-Za-z0-9-_.]+)", t))
    return sorted(names)

def find_metallb_pools():
    pools=[]
    for _, t in grep_yaml("IPAddressPool"):
        if "metallb.io" not in t: continue
        m = re.search(r"addresses:\s*\[\s*([^\]]+)\s*\]", t)
        if m:
            pools.append(m.group(1).strip())
            continue
        m2 = re.search(r"addresses:\s*\n(\s*-\s*[^\n]+(\n\s*-\s*[^\n]+)*)", t, re.M)
        if m2:
            addrs = [x.strip().lstrip("-").strip() for x in m2.group(1).splitlines() if x.strip().startswith("-")]
            pools.append(", ".join(addrs))
    # unique
    seen=set(); uniq=[]
    for x in pools:
        if x not in seen:
            seen.add(x); uniq.append(x)
    return uniq

def find_k8s_workloads():
    apps=set()
    for _, t in grep_yaml("kind:"):
        for kind, name in re.findall(r"kind:\s*(Deployment|StatefulSet|DaemonSet)\s*\n[\s\S]*?name:\s*([A-Za-z0-9-_.]+)", t):
            apps.add(name.strip())
    return sorted(apps)

def parse_inventory():
    paths = ["ansible/inventory/hosts","ansible/inventory.ini","ansible/hosts","ansible/inventory.yaml","ansible/inventory.yml"]
    hosts=[]
    for p in paths:
        t=read_text(p)
        if not t: continue
        grp=None
        for line in t.splitlines():
            line=line.strip()
            if not line or line.startswith("#") or line.startswith(";"): continue
            m=re.match(r"\[(.+?)\]", line)
            if m: grp=m.group(1); continue
            if re.match(r"^[A-Za-z0-9_.-]+(\s+.*)?$", line) and not line.startswith("["):
                hn=line.split()[0]; hosts.append((hn, grp or "nodes"))
        if hosts: break
    return hosts

def readme_section(title):
    txt = read_text("README.md")
    if not txt: return ""
    pat = re.compile(rf"^(#{{1,6}})\s*{re.escape(title)}\s*$", re.M)
    m = pat.search(txt)
    if not m: return ""
    start=m.end()
    lvl=len(m.group(1))
    nxt=re.search(rf"^#{{1,{lvl}}}\s+", txt[start:], re.M)
    body = txt[start:start+nxt.start()] if nxt else txt[start:]
    return body.strip()

def memory_bank_links(keywords, limit=30):
    items=[]
    if MB.exists():
        for p in sorted(MB.glob("*.md")):
            name=p.name.lower()
            text=read_text(p)
            if any(k in name for k in keywords) or any(k in text.lower() for k in keywords):
                title = (text.splitlines()[0].strip("# ").strip() if text.startswith("#") else p.stem.replace("-", " "))
                items.append((title, f"memory_bank/{p.name}"))
    return items[:limit]

# ---------- builders ----------
def build_home():
    banner = "images/wiki-banner.svg"
    divider = "images/accent-divider.svg"
    write_text(WIKI/"Home.md", f"""
<p align="center"><img src="{banner}" alt="SeaDogger Homelab — Wiki" width="100%"/></p>
<p align="center"><img src="{divider}" alt="" width="70%"/></p>

> **Docs live here.** Edit files under `docs/wiki/**`. On push to the default branch, CI mirrors them to the GitHub Wiki. Regeneration only happens when you manually run the workflow with `autogen=true`.

## Quick Links

| Overview | Architecture | Bootstrap | GitOps/IaC | Storage | Networking | Security |
|---|---|---|---|---|---|---|
| [[01-Overview]] | [[02-Architecture]] | [[04-Bootstrap-and-Cold-Start]] | [[05-GitOps-and-IaC]] | [[06-Storage-Rook-Ceph]] | [[07-Networking-and-Ingress]] | [[08-Security-and-Certificates]] |

| Apps | Benchmarking | Runbooks | Troubleshooting | ADRs | Memory Bank | Images |
|---|---|---|---|---|---|---|
| [[09-Apps]] | [[10-Benchmarking]] | [[11-Runbooks]] | [[12-Troubleshooting]] | [[13-ADR-Index]] | [[14-Memory-Bank-Index]] | [[Images-Index]] |
""".strip()+"\n")

def build_overview():
    rm = read_text("README.md")
    imgs = list_images(keys=("arch","overview","topology"))
    L=[]
    L.append("# Overview")
    L.append(f"*Generated — {now_utc()}*")
    L.append("")
    if imgs:
        L.append(f"![Overview]({imgs[0]})\n")
    if rm:
        L.append("## From README\n")
        L.append(rm.strip())
        L.append("")
    write_text(WIKI/"01-Overview.md", "\n".join(L))

def build_architecture():
    rm_arch = readme_section("Architecture")
    imgs = list_images(keys=("arch","topology","diagram","rack","layout"))
    pools = find_metallb_pools()
    scs = find_storageclasses()
    apps = find_k8s_workloads()
    mbl  = memory_bank_links(["arch","topology","rook","ceph","design","storage","metallb","traefik","ingress"])

    L=[]
    L.append("# Architecture")
    L.append(f"*Generated — {now_utc()}*")
    L.append("")
    if imgs:
        L.append(f"![Architecture]({imgs[0]})\n")
        if len(imgs)>1:
            L.append("> **More diagrams**")
            for x in imgs[1:6]: L.append(f"- ![]({x})")
            L.append("")
    if rm_arch:
        L.append("## From README\n")
        L.append(rm_arch)
        L.append("")
    if pools:
        L.append("## MetalLB Address Pools (discovered)")
        for p in pools: L.append(f"- `{p}`")
        L.append("")
    if scs:
        L.append("## StorageClasses (discovered)")
        for s in scs: L.append(f"- `{s}`")
        L.append("")
    if apps:
        L.append("## Workloads (discovered)")
        for a in apps: L.append(f"- `{a}`")
        L.append("")
    if mbl:
        L.append("## From the Memory Bank")
        for t, href in mbl: L.append(f"- [{t}]({href})")
        L.append("")
    write_text(WIKI/"02-Architecture.md", "\n".join(L))

def build_hardware():
    hosts = parse_inventory()
    imgs = list_images(keys=("rack","layout","wiring","switch","nvme","bom"))
    mbl  = memory_bank_links(["hardware","nvme","ssd","rack","bom","switch","power","thermal","network","ip plan","partition"])

    L=[]
    L.append("# Hardware & Network")
    L.append(f"*Generated — {now_utc()}*")
    L.append("")
    if imgs: L.append(f"![Rack]({imgs[0]})\n")
    L.append("## Bill of Materials (example)")
    L.append("- Raspberry Pi 5 nodes")
    L.append("- NVMe per node")
    L.append("- Managed switch, UPS")
    L.append("")
    if hosts:
        L.append("## Nodes (from Ansible inventory)")
        L.append("| Host | Group |")
        L.append("|---|---|")
        for h,g in hosts: L.append(f"| `{h}` | {g} |")
        L.append("")
    if mbl:
        L.append("## From the Memory Bank")
        for t, href in mbl: L.append(f"- [{t}]({href})")
        L.append("")
    write_text(WIKI/"03-Hardware-and-Network.md", "\n".join(L))

def build_bootstrap():
    flags = read_text("ansible/group_vars/all/config.yml") or read_text("ansible/group_vars/all/config.yaml")
    mbl  = memory_bank_links(["cold start","bootstrap","wipe","cleanup","finalizer","stage","flag","ansible","k3s"])

    L=[]
    L.append("# Bootstrap & Cold Start (IaC)")
    L.append(f"*Generated — {now_utc()}*")
    L.append("")
    L.append("## Stages")
    L.append("- **Stage 1 – Core Infra:** Node prep → K3s → Rook-Ceph → MetalLB")
    L.append("- **Stage 2 – Platform Infra:** ArgoCD (Helm) → Traefik + TLS base")
    L.append("- **Stage 3 – Apps:** Observability → Apps\n")
    if flags:
        L.append("## Current Flags (from `ansible/group_vars/all/config.yml`)")
        L.append("```yaml")
        L.append(flags.strip())
        L.append("```\n")
    L.append("## Enforcement Patterns")
    L.append("```yaml\nwhen:\n  - stages.infra_core | default(false) | bool\n  - components.rook_ceph | default(false) | bool\n```")
    L.append("```yaml\nwhen:\n  - stages.apps | default(false) | bool\n  - apps.plex | default(false) | bool\n```\n")
    L.append("## Clean/Wipe")
    L.append("- Remove finalizers; delete stuck namespaces; wipe storage only when intended.")
    L.append("- After wipe, re-run Stage 1 → Stage 2 → Stage 3 progressively.\n")
    if mbl:
        L.append("## From the Memory Bank")
        for t, href in mbl: L.append(f"- [{t}]({href})")
        L.append("")
    write_text(WIKI/"04-Bootstrap-and-Cold-Start.md", "\n".join(L))

def build_gitops():
    argocd = bool(grep_yaml("argoproj.io"))
    helm   = bool(grep_yaml("apiVersion: v2")) or bool(grep_yaml("Chart.yaml"))
    ansible= bool(read_text("ansible/playbook.yml") or read_text("ansible/site.yml"))
    mbl = memory_bank_links(["gitops","argocd","helm","ansible","iac","cleanup","wipe","apps after infra"])

    L=[]
    L.append("# GitOps & IaC")
    L.append(f"*Generated — {now_utc()}*")
    L.append("")
    L.append("## Workflow")
    L.append("- Edit code/docs → PR → merge to **default branch** → CI publishes wiki.")
    L.append("- Infra via ArgoCD (app-of-apps); Ansible bootstraps; Helm charts tracked in repo.")
    L.append("- **Apps only after Stage 1 & 2 healthy**; enable apps gradually.\n")
    L.append("## Signals Seen")
    L.append(f"- ArgoCD present: {'yes' if argocd else 'no'}")
    L.append(f"- Helm charts detected: {'yes' if helm else 'no'}")
    L.append(f"- Ansible playbooks present: {'yes' if ansible else 'no'}\n")
    if mbl:
        L.append("## From the Memory Bank")
        for t, href in mbl: L.append(f"- [{t}]({href})")
        L.append("")
    write_text(WIKI/"05-GitOps-and-IaC.md", "\n".join(L))

def build_storage():
    scs = find_storageclasses()
    imgs = list_images(keys=("ceph","rbd","cephfs","storage"))
    mbl  = memory_bank_links(["ceph","rbd","cephfs","osd","mds","erasure","storageclass","rook"])
    rook = bool(grep_yaml("rook-ceph"))

    L=[]
    L.append("# Storage: Rook-Ceph")
    L.append(f"*Generated — {now_utc()}*")
    L.append("")
    if imgs: L.append(f"![]({imgs[0]})\n")
    L.append("## Overview")
    L.append("- RBD default; CephFS with EC for bulk; MDS 1 active + 1 standby.\n")
    if scs:
        L.append("## StorageClasses (discovered)")
        for s in scs: L.append(f"- `{s}`")
        L.append("")
    L.append(f"Rook detected in manifests: {'yes' if rook else 'no'}\n")
    if mbl:
        L.append("## From the Memory Bank")
        for t, href in mbl: L.append(f"- [{t}]({href})")
        L.append("")
    write_text(WIKI/"06-Storage-Rook-Ceph.md", "\n".join(L))

def build_networking():
    pools = find_metallb_pools()
    imgs  = list_images(keys=("network","metallb","ingress","traefik","dns"))
    traefik = bool(grep_yaml("traefik"))
    mbl   = memory_bank_links(["metallb","traefik","ingress","dns","pihole","network"])

    L=[]
    L.append("# Networking & Ingress")
    L.append(f"*Generated — {now_utc()}*")
    L.append("")
    if imgs: L.append(f"![]({imgs[0]})\n")
    if pools:
        L.append("## MetalLB Address Pools")
        for p in pools: L.append(f"- `{p}`")
        L.append("")
    L.append(f"Traefik detected in manifests: {'yes' if traefik else 'no'}\n")
    if mbl:
        L.append("## From the Memory Bank")
        for t, href in mbl: L.append(f"- [{t}]({href})")
        L.append("")
    write_text(WIKI/"07-Networking-and-Ingress.md", "\n".join(L))

def build_security():
    mbl = memory_bank_links(["cert","tls","ca","acme","keycloak","oauth2"])
    L=[]
    L.append("# Security & Certificates")
    L.append(f"*Generated — {now_utc()}*")
    L.append("")
    L.append("```mermaid")
    L.append("sequenceDiagram")
    L.append("  autonumber")
    L.append("  actor User as Browser")
    L.append("  participant Traefik")
    L.append("  participant ACME as Let's Encrypt")
    L.append("  User->>Traefik: HTTPS")
    L.append("  Traefik->>ACME: DNS-01/HTTP-01")
    L.append("  ACME-->>Traefik: Cert")
    L.append("  Traefik-->>User: TLS")
    L.append("```")
    L.append("")
    if mbl:
        L.append("## From the Memory Bank")
        for t, href in mbl: L.append(f"- [{t}]({href})")
        L.append("")
    write_text(WIKI/"08-Security-and-Certificates.md", "\n".join(L))

def build_apps():
    apps = find_k8s_workloads()
    imgs = list_images(keys=("app","dashboard","grafana","pihole","openwebui","plex"))
    mbl  = memory_bank_links(["plex","n8n","openwebui","bedrock","prometheus","grafana","alertmanager","pihole"])

    L=[]
    L.append("# Applications")
    L.append(f"*Generated — {now_utc()}*")
    L.append("")
    if imgs: L.append(f"![]({imgs[0]})\n")
    if apps:
        L.append("## Discovered Workloads")
        for a in apps: L.append(f"- `{a}`")
        L.append("")
    if mbl:
        L.append("## From the Memory Bank")
        for t, href in mbl: L.append(f"- [{t}]({href})")
        L.append("")
    write_text(WIKI/"09-Apps.md", "\n".join(L))

def build_benchmarking():
    # Very light log scan (fio/iperf/sysbench); include first 80 lines
    items=[]
    for p in ROOT.rglob("*"):
        if p.suffix.lower() not in {".log",".txt",".md"}: continue
        nm=p.name.lower()
        if any(k in nm for k in ("fio","iperf","sysbench","benchmark")):
            text=read_text(p)
            if text: items.append((str(p), text))
        if len(items)>=20: break

    L=[]
    L.append("# Benchmarking")
    L.append(f"*Generated — {now_utc()}*")
    L.append("")
    if items:
        for path, text in items:
            L.append(f"### {path}\n")
            L.append("```")
            L.append("\n".join(text.splitlines()[:80]))
            L.append("```\n")
    else:
        L.append("_No benchmark logs found in repo. Add fio/iperf/sysbench outputs to include them here._")
    write_text(WIKI/"10-Benchmarking.md", "\n".join(L))

def build_runbooks():
    mbl = memory_bank_links(["runbook","migrate","pvc","rotate","dashboard","playbook","recovery","backup","restore","cold start"])
    L=[]
    L.append("# Runbooks")
    L.append(f"*Generated — {now_utc()}*")
    L.append("")
    if mbl:
        L.append("## Curated Procedures")
        for t, href in mbl: L.append(f"- [{t}]({href})")
        L.append("")
    else:
        L.append("_Add runbook notes to memory_bank to surface them here._")
    write_text(WIKI/"11-Runbooks.md", "\n".join(L))

def build_troubleshooting():
    mbl = memory_bank_links(["troubleshoot","error","failed","CrashLoop","Pending","finalizer","stuck","timeout","ingress","tls","metallb","rook","ceph"])
    L=[]
    L.append("# Troubleshooting")
    L.append(f"*Generated — {now_utc()}*")
    L.append("")
    if mbl:
        L.append("## Known Issues & Fixes")
        for t, href in mbl: L.append(f"- [{t}]({href})")
        L.append("")
    else:
        L.append("_Add troubleshooting notes to memory_bank to surface them here._")
    write_text(WIKI/"12-Troubleshooting.md", "\n".join(L))

def build_adr_index():
    adrs=[]
    for p in ROOT.rglob("ADR-*.md"):
        adrs.append(str(p))
    L=[]
    L.append("# ADR Index")
    L.append(f"*Generated — {now_utc()}*")
    L.append("")
    if adrs:
        for a in sorted(adrs): L.append(f"- `{a}`")
        L.append("")
    else:
        L.append("_No ADR-*.md files found. Add ADRs at repo root or under docs._")
    write_text(WIKI/"13-ADR-Index.md", "\n".join(L))

def build_images_index():
    L=[]
    L.append("# Images")
    L.append(f"*Generated gallery from docs/wiki/images — {now_utc()}*")
    L.append("")
    if IMAGES.exists():
        for p in sorted(IMAGES.glob("*")):
            if p.is_dir(): continue
            rel=f"images/{p.name}"
            L.append(f"![{p.name}]({rel})")
    else:
        L.append("_No images found under docs/wiki/images._")
    write_text(WIKI/"Images-Index.md", "\n".join(L))

def build_memory_bank_index():
    rows=[]
    for p in sorted(MB.glob("*.md")):
        text=read_text(p)
        title=(text.splitlines()[0].strip("# ").strip() if text.startswith("#") else p.stem.replace("-", " "))
        m=re.match(r"(20\d{2}-\d{2}-\d{2})", p.name)
        date=m.group(1) if m else "-"
        tag_text=text.lower()
        tags=[]
        if any(k in tag_text for k in ["ceph","rbd","cephfs","osd","mds","storageclass","erasure"]): tags.append("Storage")
        if any(k in tag_text for k in ["metallb","traefik","ingress","dns","pihole"]): tags.append("Networking")
        if any(k in tag_text for k in ["argocd","helm","ansible","iac","gitops","cleanup","wipe"]): tags.append("GitOps/IaC")
        if any(k in tag_text for k in ["cert","tls","ca","acme","keycloak","oauth2-proxy"]): tags.append("Security/Certs")
        if any(k in tag_text for k in ["prometheus","grafana","alertmanager","observability"]): tags.append("Observability")
        if any(k in tag_text for k in ["plex","n8n","openwebui","bedrock"]): tags.append("Apps")
        rows.append((date, title, p.name, ", ".join(sorted(set(tags)) or ["Misc"])))
    rows.sort(key=lambda r:(r[0], r[2]), reverse=True)
    L=[]
    L.append("# Memory Bank Index")
    L.append(f"_Auto-generated from `docs/wiki/memory_bank/*.md` — {now_utc()}_")
    L.append("")
    L.append("| Date | Title | File | Tags |")
    L.append("|---|---|---|---|")
    for date, title, name, tags in rows:
        L.append(f"| {date} | [{title}](memory_bank/{name}) | `{name}` | {tags} |")
    write_text(WIKI/"14-Memory-Bank-Index.md", "\n".join(L))

def summarize_memory_into_topics():
    buckets={"Storage":[], "Networking":[], "GitOps/IaC":[], "Security/Certs":[], "Apps":[]}
    for p in sorted(MB.glob("*.md")):
        txt=read_text(p).lower()
        title=(read_text(p).splitlines()[0].strip("# ").strip() if read_text(p).startswith("#") else p.stem.replace("-", " "))
        rel=f"memory_bank/{p.name}"
        if any(k in txt for k in ["ceph","rbd","cephfs","mds","erasure","storageclass"]): buckets["Storage"].append((title, rel))
        if any(k in txt for k in ["metallb","traefik","ingress","dns","pihole"]): buckets["Networking"].append((title, rel))
        if any(k in txt for k in ["argocd","helm","ansible","iac","gitops","cleanup","wipe"]): buckets["GitOps/IaC"].append((title, rel))
        if any(k in txt for k in ["cert","tls","ca","acme","keycloak","oauth2-proxy"]): buckets["Security/Certs"].append((title, rel))
        if any(k in txt for k in ["plex","n8n","openwebui","bedrock"]): buckets["Apps"].append((title, rel))
    targets={
        "Storage": WIKI/"06-Storage-Rook-Ceph.md",
        "Networking": WIKI/"07-Networking-and-Ingress.md",
        "GitOps/IaC": WIKI/"05-GitOps-and-IaC.md",
        "Security/Certs": WIKI/"08-Security-and-Certificates.md",
        "Apps": WIKI/"09-Apps.md",
    }
    for key, items in buckets.items():
        if not items: continue
        p = targets[key]
        md = read_text(p) or f"# {p.stem}\n\n"
        md = re.sub(r"\n## From the Memory Bank[\s\S]*$", "", md, flags=re.M|re.S)
        md += "\n\n## From the Memory Bank\n\n"
        for title, rel in items:
            md += f"- [{title}]({rel})\n"
        write_text(p, md)

def main():
    ensure_dirs()
    # Core pages
    build_home()
    build_overview()
    build_architecture()
    build_hardware()
    build_bootstrap()
    build_gitops()
    build_storage()
    build_networking()
    build_security()
    build_apps()
    build_benchmarking()
    build_runbooks()
    build_troubleshooting()
    build_adr_index()
    build_images_index()
    # Memory bank indexes/backlinks
    build_memory_bank_index()
    summarize_memory_into_topics()
    print("All wiki pages generated under docs/wiki/")

if __name__ == "__main__":
    main()
