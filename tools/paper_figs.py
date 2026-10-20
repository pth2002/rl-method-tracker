"""Figures for the report, all from data/generated. One command rebuilds every figure.

  python tools/paper_figs.py   ->  paper/figs/{overview,landing,landing_all,components,casecontrol_all}.pdf

Every figure is drawn at the width it takes in the report (5.5 in, the text width), so font sizes
here are the printed sizes. Labels sit outside the data area, the layout is fitted to the measured
size of every label, and check_layout() reports any text that touches another text, a marker, a
line or a bar before the figure is saved.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import date
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402
from matplotlib.transforms import Bbox, offset_copy  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
GEN = ROOT / "data" / "generated"
OUT = ROOT / "paper" / "figs"
BLUE, ORANGE, GRAY, INK, MUTED = "#2a78d6", "#eb6834", "#b4b2a9", "#0b0b0b", "#52514e"
WIDTH = 5.5           # inches, the text width of the report
PAD = 0.04            # inches of white space kept around the content
FS_TICK, FS_NOTE, FS_LABEL, FS_TITLE = 7.5, 7.5, 8.0, 8.0

# STIX matches the Times body text of the report and is free to embed
plt.rcParams.update({
    "font.family": "STIXGeneral", "mathtext.fontset": "stix", "font.size": FS_LABEL,
    "axes.titlesize": FS_TITLE, "axes.labelsize": FS_LABEL,
    "xtick.labelsize": FS_TICK, "ytick.labelsize": FS_TICK, "legend.fontsize": FS_NOTE,
    "axes.edgecolor": MUTED, "axes.linewidth": 0.6, "xtick.major.width": 0.6, "ytick.major.width": 0.6,
    "xtick.color": MUTED, "ytick.color": MUTED, "xtick.labelcolor": INK, "ytick.labelcolor": INK,
    "axes.labelcolor": INK, "text.color": INK,
    "axes.spines.top": False, "axes.spines.right": False, "pdf.fonttype": 42,
})


def read_jsonl(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text(encoding="utf-8").split(chr(10)) if l.strip()]


SHORT = {
    "dapo_clip_higher": "Clip-higher (DAPO)", "dapo_dynamic_sampling": "Dynamic sampling (DAPO)",
    "dapo_token_loss": "Token-level loss (DAPO)", "dapo_overlong": "Overlong shaping (DAPO)",
    "dapo_no_kl": "No KL penalty (DAPO)", "tis": "TIS", "mis": "MIS", "dr_grpo": "Dr. GRPO",
    "reinforce_pp": "REINFORCE++", "intellect2_two_sided_clip": "Two-sided clip (INTELLECT-2)",
    "skywork_adaptive_entropy": "Adaptive entropy (Skywork-OR1)", "areal_decoupled": "Decoupled PPO (AReaL)",
    "high_entropy_tokens": "High-entropy tokens", "routing_replay": "Routing replay",
    "r3_rollout_routing_replay": "Rollout routing replay (R3)", "rep_exp": "Representation exploration",
    "unbiased_kl": "Unbiased KL (DeepSeek-V3.2)", "opsm": "Sequence masking (DeepSeek-V3.2)",
    "optimal_token_baseline": "Optimal token baseline", "passk_advantage": "Pass@k advantage",
    "flash_reinforce": "FlashREINFORCE", "entropy_cov": "Clip-Cov and KL-Cov", "bema_ref": "BEMA reference",
}


# ---------------------------------------------------------------- layout helpers

def _extents(fig, ax):
    """Space that the labels of one axes take beyond its plot area, in figure fractions."""
    fig.canvas.draw()
    r = fig.canvas.get_renderer()
    tb = ax.get_tightbbox(r).transformed(fig.transFigure.inverted())
    pos = ax.get_position()
    return pos.x0 - tb.x0, tb.x1 - pos.x1, pos.y0 - tb.y0, tb.y1 - pos.y1


def fit_single(fig, ax, top_extra_in: float = 0.0) -> None:
    """Grow the plot area until its labels reach the figure edge, keeping PAD of white space."""
    w, h = fig.get_size_inches()
    px, py = PAD / w, PAD / h
    for _ in range(4):
        left, right, bottom, top = _extents(fig, ax)
        top += top_extra_in / h
        ax.set_position([px + left, py + bottom, 1 - 2 * px - left - right, 1 - 2 * py - bottom - top])


def fit_row(fig, axes, ratios, gap_in: float, top_in: float) -> None:
    """Place axes side by side so that the label blocks of neighbours are gap_in apart."""
    w, h = fig.get_size_inches()
    px, py, gap = PAD / w, PAD / h, gap_in / w
    for _ in range(4):
        ext = [_extents(fig, ax) for ax in axes]
        bottom = max(e[2] for e in ext)
        avail = 1 - 2 * px - sum(e[0] + e[1] for e in ext) - gap * (len(axes) - 1)
        x = px
        for ax, e, r in zip(axes, ext, ratios):
            x += e[0]
            width = avail * r / sum(ratios)
            ax.set_position([x, py + bottom, width, 1 - 2 * py - bottom - top_in / h])
            x += width + e[1] + gap


def _text_boxes(fig):
    """Every drawn text of the figure with its box in display units."""
    fig.canvas.draw()
    r = fig.canvas.get_renderer()
    out = []
    for ax in fig.axes:
        xlo, xhi = sorted(ax.get_xlim())
        ylo, yhi = sorted(ax.get_ylim())
        for t, loc in [(t, x) for t, x in zip(ax.get_xticklabels(), ax.get_xticks())]:
            if t.get_text() and xlo <= loc <= xhi:
                out.append((t.get_text(), t.get_window_extent(r)))
        for t, loc in [(t, y) for t, y in zip(ax.get_yticklabels(), ax.get_yticks())]:
            if t.get_text() and ylo <= loc <= yhi:
                out.append((t.get_text(), t.get_window_extent(r)))
        for t in [ax.xaxis.label, ax.yaxis.label, ax.title, *ax.texts]:
            if t.get_visible() and t.get_text().strip() and t.get_gid() != "inmarker":
                out.append((t.get_text(), t.get_window_extent(r)))
        leg = ax.get_legend()
        if leg:
            out += [(t.get_text(), t.get_window_extent(r)) for t in leg.get_texts()]
    for t in fig.texts:
        if t.get_text().strip():
            out.append((t.get_text(), t.get_window_extent(r)))
    for leg in fig.legends:
        out += [(t.get_text(), t.get_window_extent(r)) for t in leg.get_texts()]
    return out


def check_layout(fig, name: str, margin_pt: float = 1.0) -> None:
    """Report texts that touch each other, a marker, a plotted line or a bar, or leave the figure."""
    boxes = _text_boxes(fig)
    k = fig.dpi / 72
    m = margin_pt * k
    problems = []
    fw, fh = fig.bbox.width, fig.bbox.height
    for s, b in boxes:
        if b.x0 < -0.5 or b.y0 < -0.5 or b.x1 > fw + 0.5 or b.y1 > fh + 0.5:
            problems.append(f"outside the figure: {s!r}")
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            (s1, a), (s2, b) = boxes[i], boxes[j]
            if a.x0 < b.x1 + m and b.x0 < a.x1 + m and a.y0 < b.y1 + m and b.y0 < a.y1 + m:
                problems.append(f"text on text: {s1!r} / {s2!r}")

    def hits(b, x, y, rad):
        cx, cy = min(max(x, b.x0), b.x1), min(max(y, b.y0), b.y1)
        return (cx - x) ** 2 + (cy - y) ** 2 < (rad + m) ** 2

    for ax in fig.axes:
        for ln in ax.lines:
            if not ln.get_visible() or len(ln.get_xdata()) == 0:
                continue
            pts = ax.transData.transform(list(zip(ln.get_xdata(), ln.get_ydata())))
            marker = ln.get_marker()
            if marker not in (None, "", "None", " "):
                rad = (ln.get_markersize() / 2 + ln.get_markeredgewidth() / 2) * k
                for s, b in boxes:
                    if any(hits(b, x, y, rad) for x, y in pts):
                        problems.append(f"text on marker: {s!r}")
            if ln.get_linestyle() not in ("None", "", " ") and len(pts) > 1:
                half = ln.get_linewidth() / 2 * k
                for s, b in boxes:
                    for (x0, y0), (x1, y1) in zip(pts[:-1], pts[1:]):
                        steps = max(2, int(max(abs(x1 - x0), abs(y1 - y0)) / 2))
                        if any(hits(b, x0 + (x1 - x0) * t / steps, y0 + (y1 - y0) * t / steps, half)
                               for t in range(steps + 1)):
                            problems.append(f"text on line: {s!r}")
                            break
        for p in ax.patches:
            if isinstance(p, Rectangle) and p.get_visible():
                # a bar is drawn clipped to its axes, and a bar from zero on a log axis reaches -inf
                rb = Bbox.intersection(p.get_window_extent(), ax.bbox) if p.get_clip_on() else p.get_window_extent()
                if rb is None:
                    continue
                for s, b in boxes:
                    if b.x0 < rb.x1 + m and rb.x0 < b.x1 + m and b.y0 < rb.y1 + m and rb.y0 < b.y1 + m:
                        problems.append(f"text on bar: {s!r}")
    # a count written inside a mark must fit inside it
    for ax in fig.axes:
        for t in ax.texts:
            if t.get_gid() == "inmarker":
                b = t.get_window_extent(fig.canvas.get_renderer())
                cx, cy = ax.transData.transform((t.get_position()))
                ln = next(l for l in ax.lines if l.get_gid() == "cluster" and abs(l.get_ydata()[0] - t.get_position()[1]) < 1e-9)
                rad = ln.get_markersize() / 2 * k
                # the text box includes the line's leading, so its height is compared more loosely
                if b.width / 2 > rad * 0.8 or b.height / 2 > rad * 1.1:
                    problems.append(f"count does not fit its mark: {t.get_text()!r}")
    problems = sorted(set(problems))
    print(f"{name}: " + ("layout ok" if not problems else "; ".join(problems)))


def save(fig, name: str) -> None:
    check_layout(fig, name)
    fig.savefig(OUT / name)
    plt.close(fig)


class NumberedMark:
    """Legend stand-in for the larger mark that carries a count."""

    def __init__(self, ms: float, number: str, fs: float):
        self.ms, self.number, self.fs = ms, number, fs


class NumberedMarkHandler:
    def legend_artist(self, legend, orig, fontsize, box):
        from matplotlib.text import Text
        x = box.xdescent + box.width / 2
        y = box.ydescent + box.height / 2
        dot = Line2D([x], [y], ls="", marker="o", ms=orig.ms, mfc=BLUE, mec=BLUE, mew=0.9,
                     transform=box.get_transform())
        num = Text(x, y, orig.number, ha="center", va="center_baseline", fontsize=orig.fs, color="white",
                   transform=box.get_transform())
        box.add_artist(dot)
        box.add_artist(num)
        return dot


# ---------------------------------------------------------------- figures

def landing(min_frameworks: int = 1, name: str = "landing.pdf") -> None:
    rows = json.loads((GEN / "adoption.json").read_text(encoding="utf-8"))
    rows = [r for r in rows if r["n_frameworks_ever"] >= min_frameworks]
    # methods whose every landing predates the parseable history have no lag to show
    rows = [r for r in rows if (r["source_date"] or "") >= "2025-01-01" and len(r["source_date"]) == 10
            and r["per_framework"]]
    rows.sort(key=lambda r: (-r["n_frameworks_at_head"], r["source_date"]))
    full = len(rows) > 20
    row_h = 0.128 if full else 0.19
    ms = 3.6 if full else 4.4
    fs = 7.0 if full else FS_TICK
    fig = plt.figure(figsize=(WIDTH, row_h * len(rows) + 0.85))
    ax = fig.add_axes([0.3, 0.1, 0.65, 0.8])
    max_lag = 0
    counts = []
    # marks closer than one marker width would hide each other, so they are spread up and down
    # within the row; the step keeps the outermost mark inside its row
    days_per_pt = 505 / (0.72 * WIDTH * 72)
    near = ms * days_per_pt
    diam = (ms + 0.9) / (row_h * 72)          # marker width in row units, edge included
    for i, r in enumerate(rows):
        y = len(rows) - 1 - i
        src = date.fromisoformat(r["source_date"])
        marks = []
        for fw, v in r["per_framework"].items():
            d = (date.fromisoformat(v["first_date"]) - src).days
            max_lag = max(max_lag, d)
            kind = "bound" if v["left_censored"] else (
                "author" if v["commit_author_is_paper_author"] == "author" else "other")
            marks.append((d, kind))
        marks.sort()
        groups, cur = [], [marks[0]]
        for m in marks[1:]:
            if m[0] - cur[-1][0] < near:
                cur.append(m)
            else:
                groups.append(cur)
                cur = [m]
        groups.append(cur)
        if len(marks) > 1:
            ax.plot([marks[0][0], marks[-1][0]], [y, y], color=GRAY, lw=0.8, zorder=1, solid_capstyle="butt")
        for g in groups:
            if len(g) >= 3 and len({k for _, k in g}) == 1 and g[0][1] == "other":
                # more landings than a row can hold side by side: one larger mark carries their count
                x = sum(d for d, _ in g) / len(g)
                ax.plot(x, y, "o", ms=ms * 1.9, mfc=BLUE, mec=BLUE, mew=0.9, zorder=4, gid="cluster")
                ax.text(x, y, str(len(g)), ha="center", va="center_baseline", fontsize=fs * 0.95,
                        color="white", zorder=5, gid="inmarker")
                counts.append(len(g))
                continue
            # neighbours touch, and the outermost mark stays inside its row
            sep = diam if len(g) == 1 else min(diam, (0.5 - diam / 2) / ((len(g) - 1) / 2))
            offs = [sep * (j - (len(g) - 1) / 2) for j in range(len(g))]
            for (d, kind), dy in zip(g, offs):
                if kind == "bound":
                    ax.plot(d, y + dy, "x", ms=ms * 0.95, color=MUTED, mew=0.9, zorder=3)
                else:
                    ax.plot(d, y + dy, "o", ms=ms, mfc="white" if kind == "author" else BLUE, mec=BLUE,
                            mew=0.9, zorder=3)
    labels = [SHORT.get(r["id"], r["name"].split(" (")[0]) for r in rows]
    # method names are tick labels outside the plot, so an early landing never sits on a name
    ax.set_yticks(range(len(rows))[::-1], labels, fontsize=fs)
    ax.tick_params(axis="y", length=0, pad=4)
    ax.spines["left"].set_visible(False)
    ax.set_ylim(-0.7, len(rows) - 0.3)
    ax.axvline(0, color=MUTED, lw=0.6, ls=(0, (2, 2)), zorder=0)
    ax.set_xlim(-80, max(420, max_lag + 25))
    ax.set_xticks([0, 100, 200, 300, 400])
    ax.set_xlabel("Days from the first public version to a main branch", labelpad=3)
    handles = [Line2D([], [], ls="", marker="o", ms=ms, mfc=BLUE, mec=BLUE, label="Other commit author"),
               Line2D([], [], ls="", marker="o", ms=ms, mfc="white", mec=BLUE, mew=0.9, label="Paper author"),
               Line2D([], [], ls="", marker="x", ms=ms * 0.95, color=MUTED, mew=0.9, label="Upper bound")]
    handler_map = {}
    if counts:
        # the numbered mark is explained where the reader looks first, next to the other marks
        n = max(counts)
        mark = NumberedMark(ms * 1.9, str(n), fs * 0.95)
        handles.append(mark)
        labels_ = [h.get_label() for h in handles[:-1]] + [f"{n} landings within a week"]
        handler_map = {NumberedMark: NumberedMarkHandler()}
    else:
        labels_ = [h.get_label() for h in handles]
    ax.legend(handles=handles, labels=labels_, handler_map=handler_map, loc="lower center",
              bbox_to_anchor=(0.5, 1.0), ncol=len(handles), frameon=False,
              handletextpad=0.3, columnspacing=1.4, borderaxespad=0.3)
    fit_single(fig, ax)
    save(fig, name)


def components() -> None:
    pool = read_jsonl(GEN / "pool_adoption.jsonl")
    gen = [r for r in pool if r["strict_general"]]
    by = defaultdict(list)
    for r in gen:
        if r["component"]:
            by[r["component"]].append(r)
    names = {"sampling": "Rollout sampling", "other": "Other", "advantage": "Advantage or baseline",
             "credit_assignment": "Credit assignment", "length": "Length shaping", "offpolicy": "Off-policy correction",
             "multi_reward": "Multiple rewards", "entropy": "Entropy control", "clipping": "Clipping or trust region",
             "kl": "KL regularisation", "aggregation": "Loss aggregation", "moe": "MoE routing"}
    items = sorted(((c, rs) for c, rs in by.items() if len(rs) >= 10), key=lambda kv: len(kv[1]))
    fig = plt.figure(figsize=(WIDTH, 2.45))
    ax = fig.add_axes([0.3, 0.15, 0.6, 0.8])
    for y, (c, rs) in enumerate(items):
        n, k = len(rs), sum(r["adopted"] for r in rs)
        ax.barh(y, 100 * k / n, height=0.6, color=BLUE, linewidth=0)
        ax.annotate(f"{k}/{n}", (100 * k / n, y), xytext=(3.5, 0), textcoords="offset points",
                    va="center", fontsize=FS_NOTE, color=INK)
    ax.set_yticks(range(len(items)), [names.get(c, c) for c, _ in items])
    ax.tick_params(axis="y", length=0, pad=4)
    ax.set_ylim(-0.6, len(items) - 0.4)
    ax.set_xlim(0, 10.5)
    ax.set_xticks([0, 2, 4, 6, 8, 10])
    ax.set_xlabel("General methods included in at least one framework (%)", labelpad=3)
    fit_single(fig, ax)
    save(fig, "components.pdf")


def casecontrol() -> None:
    import sys
    sys.path.insert(0, str(ROOT / "tools"))
    from casecontrol import FEATURES  # noqa: E402

    key = json.loads((ROOT / ".cache" / "casecontrol_key.json").read_text(encoding="utf-8"))
    pool = {r["arxiv"]: r for r in read_jsonl(GEN / "pool_adoption.jsonl")}
    v1p = GEN / "casecontrol" / "cc_v1_filled.jsonl"
    v1 = {g["arxiv"]: g for g in read_jsonl(v1p)} if v1p.exists() else {}
    # included papers found later by the citation audit, coded separately from v1
    v1.update({g["arxiv"]: g for g in read_jsonl(GEN / "casecontrol" / "cc_v1_audit_added.jsonl")})
    added = key.get("cases_added_by_audit", [])
    # v1 is used once every case and all but a few controls have a v1 record; a paper whose v1
    # was withdrawn has no v1 record and leaves the comparison rather than borrowing a later version
    missing_v1 = [a for a in key["cases"] + key["controls"] if a not in v1]
    use_v1 = bool(v1) and all(a in v1 for a in key["cases"]) and len(missing_v1) <= 3
    cc = v1 if use_v1 else {g["arxiv"]: g for g in read_jsonl(GEN / "casecontrol" / "cc_filled.jsonl")}
    from casecontrol import apply_overrides  # noqa: E402
    cc = apply_overrides(dict(cc))
    cases = [cc[a] for a in key["cases"] + added if a in cc and pool[a]["strict_general"]]
    ctrls = [cc[a] for a in key["controls"] if a in cc]
    feats = {fid: fn for fid, _, fn in FEATURES}
    if use_v1:
        feats["big30"] = lambda g: g.get("trained_30b_or_more")
    label = {"industry_any": "Any industry author", "industry_only": "Industry authors only",
             "code": "Links code for the method", "big30": "Trained a policy of 30B or more",
             "moe": "Trained an MoE policy", "coef": "Changes a coefficient, clip, mask or weight",
             "pipeline": "Adds a training stage or a model", "hp1": "At most one new hyperparameter (not interpreted)",
             "extra": "Needs an extra model", "failure": "Motivated by an observed training failure",
             "broad": "Evaluated beyond one domain", "compute": "Reports compute"}

    def frac(rows, fn):
        known = [g for g in rows if fn(g) is not None]
        return sum(bool(fn(g)) for g in known), len(known)

    items = []
    for fid in label:
        (k1, n1), (k0, n0) = frac(cases, feats[fid]), frac(ctrls, feats[fid])
        items.append((fid, 100 * k1 / n1, 100 * k0 / n0, f"{k1}/{n1}", f"{k0}/{n0}"))
    items.sort(key=lambda t: (t[0] != "hp1", t[1] - t[2]))
    fig = plt.figure(figsize=(WIDTH, 2.75))
    ax = fig.add_axes([0.45, 0.15, 0.35, 0.75])
    ms = 4.6
    # the two count columns sit right of the plot at fixed distances in points
    col_in = offset_copy(ax.get_yaxis_transform(), fig=fig, x=38, units="points")
    col_out = offset_copy(ax.get_yaxis_transform(), fig=fig, x=76, units="points")
    for y, (fid, a, b, sa, sb) in enumerate(items):
        # two shares within three points would hide one dot under the other, so they split vertically
        dy = 0.17 if abs(a - b) < 3 else 0.0
        if not dy:
            ax.plot([b, a], [y, y], color=GRAY, lw=0.8, zorder=1, solid_capstyle="butt")
        ax.plot(b, y - dy, "o", ms=ms, color=ORANGE, zorder=2, clip_on=False)
        ax.plot(a, y + dy, "o", ms=ms, color=BLUE, zorder=3, clip_on=False)
        ax.text(1.0, y, sa, transform=col_in, ha="right", va="center", fontsize=FS_NOTE, color=BLUE)
        ax.text(1.0, y, sb, transform=col_out, ha="right", va="center", fontsize=FS_NOTE, color=ORANGE)
    ax.set_yticks(range(len(items)), [label[f] for f, *_ in items])
    ax.tick_params(axis="y", length=0, pad=6)
    # the axis line sits a little left of zero, so a share near zero does not sit on it
    ax.spines["left"].set_position(("outward", 5))
    ax.spines["bottom"].set_bounds(0, 100)
    ax.set_ylim(-0.6, len(items) - 0.4)
    ax.set_xlim(0, 100)
    ax.set_xticks([0, 20, 40, 60, 80, 100])
    ax.set_xlabel("Share of papers that report the property (%)", labelpad=3)
    handles = [Line2D([], [], ls="", marker="o", ms=ms, color=BLUE, label=f"Included ({len(cases)})"),
               Line2D([], [], ls="", marker="o", ms=ms, color=ORANGE, label=f"Not included ({len(ctrls)})")]
    ax.legend(handles=handles, loc="lower center", bbox_to_anchor=(0.5, 1.0), ncol=2, frameon=False,
              handletextpad=0.3, columnspacing=1.6, borderaxespad=0.3)
    fit_single(fig, ax)
    save(fig, "casecontrol_all.pdf")


def overview() -> None:
    """Three findings side by side: how many methods were included, how supply and inclusion moved by
    quarter, and what the public record shows for the rest. Panel (c) shows categories, not stages."""
    pool = read_jsonl(GEN / "pool_adoption.jsonl")
    gen = [r for r in pool if r["strict_general"]]
    rec = json.loads((GEN / "process" / "summary.json").read_text(encoding="utf-8"))["funnel"]
    fig = plt.figure(figsize=(WIDTH, 2.05))
    axes = [fig.add_axes([0.1 + 0.3 * i, 0.2, 0.2, 0.6]) for i in range(3)]

    def bars(ax, items, color_of):
        ys = list(range(len(items)))[::-1]
        for y, (name, n) in zip(ys, items):
            ax.barh(y, n, height=0.6, color=color_of(n), linewidth=0)
            ax.annotate(f"{n:,}", (n, y), xytext=(3, 0), textcoords="offset points", va="center",
                        fontsize=FS_NOTE, color=INK)
        ax.set_yticks(ys, [it[0] for it in items])
        ax.set_ylim(-0.6, len(items) - 0.4)
        ax.set_xscale("log")
        ax.set_xlim(0.8, 60000)
        ax.set_xticks([])
        ax.minorticks_off()
        ax.spines["bottom"].set_visible(False)
        ax.tick_params(axis="y", length=0, pad=4)

    a = [("Pool papers", len(pool)), ("RL methods", sum(r["label"] == "rl_method" for r in pool)),
         ("General methods", len(gen)), ("In 1+ framework", sum(r["adopted"] for r in gen)),
         ("In 3+ frameworks", sum(r["n_fw_head"] >= 3 for r in gen)), ("Default", sum(r["default"] for r in gen))]
    bars(axes[0], a, lambda n: GRAY if n > 100 else BLUE)

    # (b) general methods per quarter against the number a framework took in within 180 days
    ax = axes[1]
    series = json.loads((GEN / "quarterly.json").read_text(encoding="utf-8"))
    xs = list(range(len(series)))
    sup = [s["general"] for s in series]
    inc = [s["included_180"] for s in series]
    ax.plot(xs, sup, color=GRAY, lw=1.1, marker="o", ms=3.0, zorder=2)
    ax.plot(xs, inc, color=BLUE, lw=1.1, marker="o", ms=3.0, zorder=3)
    ax.set_yscale("log")
    ax.set_ylim(1, 3000)
    ax.set_yticks([1, 10, 100, 1000], ["1", "10", "100", "1,000"])
    ax.minorticks_off()
    ticks = []
    for i, s in enumerate(series):
        q, y = s["quarter"][-2:], s["quarter"][:4]
        first_of_year = i == 0 or series[i - 1]["quarter"][:4] != y
        ticks.append(f"{q}\n{y}" if first_of_year else q)
    ax.set_xticks(xs, ticks)
    ax.tick_params(axis="x", length=2.5, pad=2)
    ax.tick_params(axis="y", length=2.5, pad=2)
    ax.set_xlim(-0.35, len(series) - 0.65)
    for vals in (sup, inc):
        ax.annotate(f"{vals[-1]}", (xs[-1], vals[-1]), xytext=(4, 0), textcoords="offset points",
                    va="center", fontsize=FS_NOTE, color=INK, annotation_clip=False)
    mid = len(series) // 2
    ax.annotate("General methods", (xs[mid], max(sup[mid - 1:mid + 2])), xytext=(0, 7),
                textcoords="offset points", ha="center", va="bottom", fontsize=FS_NOTE, color=MUTED)
    ax.annotate("Included in 180 days", (xs[mid], min(inc)), xytext=(0, -6),
                textcoords="offset points", ha="center", va="top", fontsize=FS_NOTE, color=BLUE)

    c = [("No record", rec["no_record"]), ("Cited in passing", rec["cited_only"]),
         ("Implementation PR", rec["implementation_pr"]), ("Request only", rec["request_only"])]
    bars(axes[2], c, lambda n: GRAY)

    title_in = 0.24
    fit_row(fig, axes, ratios=[0.95, 1.25, 0.9], gap_in=0.16, top_in=title_in)
    # panel titles start where each panel's labels start
    fig.canvas.draw()
    r = fig.canvas.get_renderer()
    for ax, title in zip(axes, ["(a) Inclusion", "(b) Supply and inclusion", "(c) Not included"]):
        x0 = ax.get_tightbbox(r).transformed(fig.transFigure.inverted()).x0
        fig.text(x0, 1 - PAD / fig.get_size_inches()[1], title, ha="left", va="top", fontsize=FS_TITLE)
    save(fig, "overview.pdf")


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    landing(min_frameworks=2, name="landing.pdf")
    landing(min_frameworks=1, name="landing_all.pdf")
    components()
    casecontrol()
    overview()
    print("wrote", sorted(p.name for p in OUT.glob("*.pdf")))
