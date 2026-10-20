"""Build paper/refs.bib: arXiv entries from the arXiv API (titles and authors as arXiv has them),
plus a short list of non-arXiv sources written by hand.

  python tools/make_bib.py
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
API = "http://export.arxiv.org/api/query"

# Related work and frameworks cited in the text, beyond the method catalog.
EXTRA_ARXIV = [
    "2409.19256",  # HybridFlow (verl)
    "2405.11143",  # OpenRLHF
    "2506.06122",  # ROLL
    "2505.24298",  # AReaL
    "2508.08221",  # Tricks or Traps
    "2510.13786",  # ScaleRL
    "2308.10008",  # impact of releasing code
    "1907.06902",  # recsys progress check
    "1807.03341",  # troubling trends
    "2107.07002",  # benchmark lottery
    "2003.08505",  # metric learning reality check
    "2501.12948",  # DeepSeek-R1
    "2506.09477",  # KL gradient estimation pitfalls (NeMo-RL fix case)
    "2005.12729",  # implementation matters in deep policy gradients
    "2203.11365",  # Bhatia et al., forks of ML research repositories
    # technical reports of open-weight models with 100B or more parameters, read for the report table
    "2505.00949", "2507.20534", "2508.06471", "2508.10925", "2509.18883",
    "2601.16725", "2605.26494", "2606.15007", "2606.15079",
    # reports of open-weight models with 100B or more parameters that fall outside the pool
    "2505.09388", "2505.04519", "2508.15763", "2504.00698", "2506.05767", "2507.19427",
]

MANUAL = r"""
@misc{vonwerra2020trl,
  author = {von Werra, Leandro and Belkada, Younes and Tunstall, Lewis and Beeching, Edward and Thrush, Tristan and Lambert, Nathan and Huang, Shengyi and Rasul, Kashif and Gallou{\'e}dec, Quentin},
  title = {{TRL}: Transformers Reinforcement Learning},
  year = {2020},
  howpublished = {\url{https://github.com/huggingface/trl}}
}

@misc{nemorl2025,
  key = {NeMo RL},
  title = {{NeMo RL}: A Scalable and Efficient Post-Training Library},
  year = {2025},
  howpublished = {\url{https://github.com/NVIDIA-NeMo/RL}}
}

@misc{slime2025,
  author = {Zhu, Zilin and Xie, Chengxing and Lv, Xin and {slime Contributors}},
  title = {slime: An {LLM} Post-Training Framework for {RL} Scaling},
  year = {2025},
  howpublished = {\url{https://github.com/THUDM/slime}}
}

@misc{yao2025tis,
  author = {Yao, Feng and Liu, Liyuan and Zhang, Dinghuai and Dong, Chengyu and Shang, Jingbo and Gao, Jianfeng},
  title = {Your Efficient {RL} Framework Secretly Brings You Off-Policy {RL} Training},
  year = {2025},
  month = aug,
  howpublished = {\url{https://fengyao.notion.site/off-policy-rl}}
}

@misc{schulman2020kl,
  author = {Schulman, John},
  title = {Approximating {KL} Divergence},
  year = {2020},
  howpublished = {\url{http://joschu.net/blog/kl-approx.html}}
}

@inproceedings{gousios2014pull,
  author = {Gousios, Georgios and Pinzger, Martin and van Deursen, Arie},
  title = {An Exploratory Study of the Pull-Based Software Development Model},
  booktitle = {Proceedings of the 36th International Conference on Software Engineering (ICSE)},
  pages = {345--355},
  year = {2014}
}

@inproceedings{tsay2014influence,
  author = {Tsay, Jason and Dabbish, Laura and Herbsleb, James},
  title = {Influence of Social and Technical Factors for Evaluating Contribution in {GitHub}},
  booktitle = {Proceedings of the 36th International Conference on Software Engineering (ICSE)},
  pages = {356--366},
  year = {2014}
}

@inproceedings{gousios2015integrator,
  author = {Gousios, Georgios and Zaidman, Andy and Storey, Margaret-Anne and van Deursen, Arie},
  title = {Work Practices and Challenges in Pull-Based Development: The Integrator's Perspective},
  booktitle = {Proceedings of the 37th International Conference on Software Engineering (ICSE)},
  year = {2015}
}

@inproceedings{ford2019beyond,
  author = {Ford, Denae and Behroozi, Mahnaz and Serebrenik, Alexander and Parnin, Chris},
  title = {Beyond the Code Itself: How Programmers Really Look at Pull Requests},
  booktitle = {Proceedings of the 41st International Conference on Software Engineering: Software Engineering in Society (ICSE-SEIS)},
  pages = {51--60},
  year = {2019}
}

@misc{huang2022details,
  author = {Huang, Shengyi and Dossa, Rousslan Fernand Julien and Raffin, Antonin and Kanervisto, Anssi and Wang, Weixun},
  title = {The 37 Implementation Details of Proximal Policy Optimization},
  year = {2022},
  howpublished = {ICLR Blog Track}
}

@misc{sklearnfaq,
  key = {scikit-learn},
  title = {scikit-learn {FAQ}: What are the inclusion criteria for new algorithms?},
  howpublished = {\url{https://scikit-learn.org/stable/faq.html}}
}

@article{meijer2025ecosystem,
  author = {Meijer, Willem and Riveni, Mirela and Rastogi, Ayushi},
  title = {Ecosystem-Wide Influences on Pull Request Decisions: Insights from {NPM}},
  journal = {Empirical Software Engineering},
  volume = {30},
  number = {6},
  year = {2025}
}

@article{ahmed2023industry,
  author = {Ahmed, Nur and Wahed, Muntasir and Thompson, Neil C.},
  title = {The Growing Influence of Industry in {AI} Research},
  journal = {Science},
  volume = {379},
  number = {6635},
  pages = {884--886},
  year = {2023}
}
"""


def bibkey(aid: str) -> str:
    return "arxiv" + aid.replace(".", "")


def esc(s: str) -> str:
    s = " ".join(s.split())
    # protect capitals in titles so the style keeps acronyms
    return re.sub(r"\b([A-Za-z]*[A-Z][A-Za-z0-9+\-]*[A-Z0-9][A-Za-z0-9+\-]*)\b", r"{\1}", s).replace("&", r"\&")


def main() -> None:
    papers = json.loads((ROOT / "data" / "generated" / "papers.json").read_text(encoding="utf-8"))["papers"]
    # metadata fetched for ids outside papers.json is kept, so later builds need no network
    cache_p = ROOT / "data" / "generated" / "bib_extra.json"
    cached = json.loads(cache_p.read_text(encoding="utf-8")) if cache_p.exists() else {}
    papers = {**cached, **papers}
    ids = sorted(set(papers) | set(EXTRA_ARXIV))
    need = [a for a in ids if a not in papers]
    for i in range(0, len(need), 40):
        batch = need[i:i + 40]
        text = ""
        for attempt in range(5):
            r = requests.get(API, params={"id_list": ",".join(batch), "max_results": 40}, timeout=60)
            time.sleep(3 + 5 * attempt)
            if r.ok and r.text.count("<entry>") >= len(batch):
                text = r.text
                break
        if not text:
            raise SystemExit(f"arXiv API returned no metadata for {batch}; refs.bib was not changed")
        for e in re.findall(r"<entry>(.*?)</entry>", text, re.S):
            aid = re.search(r"abs/(\d{4}\.\d{4,5})", e).group(1)
            papers[aid] = {
                "arxiv": aid,
                "title": " ".join(re.search(r"<title>(.*?)</title>", e, re.S).group(1).split()),
                "authors": re.findall(r"<name>(.*?)</name>", e),
                "published": re.search(r"<published>(\d{4}-\d\d-\d\d)", e).group(1),
            }
    cached.update({a: papers[a] for a in need if a in papers})
    cache_p.write_text(json.dumps(cached, indent=1, ensure_ascii=False), encoding="utf-8")
    out = []
    for a in ids:
        p = papers.get(a)
        if not p:
            raise SystemExit(f"no metadata for {a}; refs.bib was not changed")
        # drop placeholder entries such as ":" that some arXiv records carry after a team name
        authors = [a.strip() for a in p["authors"] if re.search(r"[A-Za-z]", a)]
        # single-word and team names are kept whole, so "Prime Intellect Team" is not cited as "Team"
        authors = [("{" + a + "}" if (" " not in a or re.search(r"\b(Team|AI|Lab|Labs)\b", a)) else a)
                   for a in authors]
        auth = " and ".join(authors[:10]) + (" and others" if len(authors) > 10 else "")
        out.append("@article{" + bibkey(a) + ",\n"
                   f"  author = {{{auth}}},\n"
                   f"  title = {{{esc(p['title'])}}},\n"
                   f"  journal = {{arXiv preprint arXiv:{a}}},\n"
                   f"  year = {{{p['published'][:4]}}}\n}}\n")
    (ROOT / "paper" / "refs.bib").write_text("\n".join(out) + MANUAL, encoding="utf-8")
    for a in EXTRA_ARXIV:
        print(a, papers.get(a, {}).get("title", "MISSING")[:90])


if __name__ == "__main__":
    main()
