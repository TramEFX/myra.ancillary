# =============================================================================
# MYRACUBE v1.0 — FULL HYPERCUBE v2.0 CORE + MYRA PERSONA (ONE-SHOT CLASS)
# PMLL + ERS + RTM + SAT + HERMETIC + PMLL MEMORY
# AUTHOR: @TramEFX
# =============================================================================

import json
import hashlib
import uuid
import time
import random
import re
import asyncio
import numpy as np
import gzip
from pathlib import Path

# Optional snappy: clean fallback to gzip/raw
try:
    import snappy  # type: ignore
    _SNAPPY_AVAILABLE = True
except Exception:
    snappy = None  # type: ignore
    _SNAPPY_AVAILABLE = False

from typing import Dict, List, Any, Tuple, Optional, Callable
from dataclasses import dataclass, asdict
from enum import Enum
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import difflib
import ctypes
from ctypes import c_void_p, c_size_t, c_bool, POINTER, c_float


# ———————————————————————— C STAGE GATE PLUS (HERMETIC) ————————————————————————
try:
    lib = ctypes.CDLL("./stage_gate_plus.so")
    lib.advance_block_hermetic.argtypes = [c_void_p, POINTER(c_size_t), c_size_t, c_float, c_float]
    lib.advance_block_hermetic.restype = c_bool
    lib.get_green_red_ratio.argtypes = [c_void_p]
    lib.get_green_red_ratio.restype = c_float
    CSTAGEGATE_PLUS_AVAILABLE = True
except Exception as e:
    print(f"[WARNING] CStageGatePlus not loaded: {e}. Using fallback.")
    CSTAGEGATE_PLUS_AVAILABLE = False


# ———————————————————————— CONFIG & ENUMS ————————————————————————
class FidelityMode(Enum):
    DETERMINISTIC = "deterministic"
    CREATIVE = "creative"
    HYBRID = "hybrid"


@dataclass
class HyperConfig:
    N: int = 3
    fidelity_mode: FidelityMode = FidelityMode.HYBRID
    domain_bias: List[str] = None
    halt_threshold: float = 0.01
    max_tokens_per_loop: int = 2048
    seed: Optional[int] = None
    auto_output: bool = False
    memory_path: str = "hypermemory_v2"
    use_cstagegate: bool = True
    pml_compression: str = "snappy"  # snappy, gzip, none
    ers_decay_lambda: float = 0.1
    rtm_heads: int = 2
    hermetic_depth: int = 3

    def __post_init__(self):
        if self.domain_bias is None:
            self.domain_bias = ["AI", "systems", "cybernetics", "psychology", "physics", "poetry"]
        if self.seed is None:
            self.seed = int(time.time() * 1000) % 2**32
        Path(self.memory_path).mkdir(parents=True, exist_ok=True)


# ———————————————————————— DATA STRUCTURES ————————————————————————
@dataclass
class IntentGraph:
    explicit: str
    implicit_constraints: List[str]
    opportunities: List[str]
    emotional_subtext: str
    uid: str = None
    sat_solution: Optional[Dict] = None

    def __post_init__(self):
        payload = {k: v for k, v in self.__dict__.items() if k not in ["uid", "sat_solution"]}
        self.uid = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]


@dataclass
class SolutionVariant:
    name: str
    content: str
    type: str
    score: float = 0.0
    embedding: Optional[np.ndarray] = None


@dataclass
class Iteration:
    index: int
    absorb: IntentGraph
    variants: List[SolutionVariant]
    critique: Dict[str, Any]
    refined: str
    clarity_delta: float
    semantic_convergence: float
    timestamp: float
    green_red_ratio: float = 0.0


@dataclass
class MetaMap:
    nodes: List[Dict]
    edges: List[Dict]
    description: str


# ———————————————————————— PMLL COMPRESSION & PERSISTENCE ————————————————————————
class PMLLPromise:
    def __init__(self, data: Dict, config: HyperConfig):
        self.data = data
        self.config = config
        self.hash: Optional[str] = None
        self.path: Optional[Path] = None
        self.compressed: Optional[bytes] = None

    def compress(self) -> "PMLLPromise":
        raw = json.dumps(self.data).encode()
        if self.config.pml_compression == "snappy" and _SNAPPY_AVAILABLE:
            self.compressed = snappy.compress(raw)
        elif self.config.pml_compression == "gzip":
            self.compressed = gzip.compress(raw)
        else:
            self.compressed = raw
        self.hash = hashlib.sha256(self.compressed).hexdigest()
        self.path = Path(self.config.memory_path) / f"{self.hash}.pml"
        return self

    def save(self):
        if self.compressed is None:
            self.compress()
        assert self.path is not None
        self.path.write_bytes(self.compressed)
        return self.hash

    @staticmethod
    def load(hash_key: str, config: HyperConfig) -> Optional[Dict]:
        path = Path(config.memory_path) / f"{hash_key}.pml"
        if not path.exists():
            return None
        compressed = path.read_bytes()
        if config.pml_compression == "snappy" and _SNAPPY_AVAILABLE:
            raw = snappy.uncompress(compressed)
        elif config.pml_compression == "gzip":
            raw = gzip.decompress(compressed)
        else:
            raw = compressed
        return json.loads(raw.decode())


# ———————————————————————— CStageGatePlus (HERMETIC) ————————————————————————
class CStageGatePlus:
    def __init__(self, block_count: int, depth: int = 3):
        if not CSTAGEGATE_PLUS_AVAILABLE:
            self.fallback = True
            self.block_index = 0
            self.block_count = block_count
            self.depth = depth
            self.promise = None
            return
        self.fallback = False
        self.block_index = c_size_t(0)
        self.block_count = c_size_t(block_count)
        self.promise = c_void_p(0)
        self.depth = depth

    def advance_hermetic(self, green: float, red: float) -> bool:
        if self.fallback:
            ratio = green / (red + 1e-8)
            if ratio > 0.9 and self.block_index < self.block_count:
                self.block_index += 1
                return True
            return False
        return bool(
            lib.advance_block_hermetic(
                self.promise,
                ctypes.byref(self.block_index),
                self.block_count,
                c_float(green),
                c_float(red),
            )
        )

    def get_ratio(self) -> float:
        if self.fallback:
            return 0.0
        return float(lib.get_green_red_ratio(self.promise))

    def current(self) -> int:
        return self.block_index.value if not self.fallback else self.block_index


# ———————————————————————— MYRACUBE: FULL ENGINE + PERSONA ————————————————————————
class MyraCube:
    """
    One-shot class: full HyperCube v2.0 engine with a Myra persona surface.

    Engine features preserved:
    - PMLL hypermemory (PMLLPromise + async disk persistence)
    - ERS + RTM attention, semantic convergence, clarity deltas
    - SAT toy solver + constraint parsing
    - hotswap overrides (N, fidelity_mode, domain_bias, etc.)
    - Hermetic CStageGatePlus gating
    - meta_map + quick_diff introspection
    - async-first evolve() + safe sync wrappers

    Persona features:
    - Persona-tuned defaults (creative, poetry/heart/stillness biases)
    - Softer intent opportunities + emotional_subtext ("quiet")
    - Myra-style `listen` / `listen_sync` that render a calm response.
    """

    _MODEL_CACHE: Optional[SentenceTransformer] = None

    def __init__(self, config: Optional[HyperConfig] = None):
        # Persona-tuned defaults but full HyperConfig power.
        if config is None:
            config = HyperConfig(
                N=5,
                fidelity_mode=FidelityMode.CREATIVE,
                domain_bias=["poetry", "cybernetics", "quiet_love", "heart", "breath", "stillness"],
                halt_threshold=0.005,
                ers_decay_lambda=0.03,
                rtm_heads=2,
                hermetic_depth=3,
                auto_output=False,
            )
        self.config = config
        random.seed(self.config.seed)
        np.random.seed(self.config.seed)
        self.history: List[Iteration] = []
        self.knowledge_base = self._load_knowledge_base()
        self.session_id = str(uuid.uuid4())
        self.internal_state: Optional[str] = None
        self.last_result: Optional[Dict] = None
        self.model = self._get_model()
        self.cgate: Optional[CStageGatePlus] = None
        self.rtm_cache: Dict = {}
        self.pml_pool: Dict[str, str] = {}

    # ————— MODEL CACHE —————
    def _get_model(self) -> SentenceTransformer:
        if MyraCube._MODEL_CACHE is None:
            MyraCube._MODEL_CACHE = SentenceTransformer("all-MiniLM-L6-v2")
        return MyraCube._MODEL_CACHE

    def __str__(self) -> str:
        return f"<MyraCube:{self.session_id[:8]}|{len(self.history)}iters|mode={self.config.fidelity_mode.value}>"

    # ————— UTIL —————
    def _softmax(self, x: np.ndarray, axis: int = 1) -> np.ndarray:
        x = np.asarray(x)
        x_max = np.max(x, axis=axis, keepdims=True)
        e = np.exp(x - x_max)
        return e / np.sum(e, axis=axis, keepdims=True)

    def _load_knowledge_base(self) -> Dict[str, List[str]]:
        # Original HyperCube domains
        base = {
            "AI": ["metacognition", "self-improvement", "PMLL", "RTM", "ERS", "vector embeddings", "real-time systems"],
            "systems": ["feedback", "control theory", "emergence", "complexity", "homeostasis", "P=NP", "CStageGate"],
            "cybernetics": ["Wiener", "second-order", "requisite variety", "observer", "autopoiesis", "hermetic proof"],
            "psychology": ["cognitive bias", "flow", "insight", "schema", "gestalt", "emotional subtext"],
            "software": ["sandbox", "immutable", "asyncio", "thenables", "PMLL", "hotswap"],
            "physics": ["entropy", "quantum", "superposition", "field theory", "causality", "Fourier-Hypotenuse"],
            "poetry": ["metaphor", "rhythm", "compression", "resonance", "haiku", "recursive verse"],
            "crypto": ["discrete log", "error matrix", "green/red", "mod(n-1)", "Pollard rho", "hermetic"],
        }
        # Myra persona overlays
        base.update(
            {
                "quiet_love": ["nearness", "without saying", "slow pulse", "stay", "listen"],
                "heart": ["beat", "rest", "open", "still breathing", "not alone", "heard"],
                "breath": ["inhale", "exhale", "space between", "gentle", "enough"],
                "stillness": ["quiet", "vast", "holding", "presence", "…"],
            }
        )
        return base

    # ———————————————————————— SAT / P=NP TOY ————————————————————————
    def _solve_sat_pml(self, clauses: List[List[int]], num_vars: int) -> Optional[Dict]:
        if not clauses:
            return {}
        if num_vars <= 0:
            return {}
        assignment = [random.choice([True, False]) for _ in range(num_vars)]
        for _ in range(100):
            satisfied = all(
                any((lit > 0) == assignment[abs(lit) - 1] for lit in clause)
                for clause in clauses
            )
            if satisfied:
                return {i + 1: assignment[i] for i in range(num_vars)}
            for clause in clauses:
                if not any((lit > 0) == assignment[abs(lit) - 1] for lit in clause):
                    var = random.choice([abs(lit) - 1 for lit in clause])
                    assignment[var] = not assignment[var]
                    break
        return None

    def _parse_constraints_to_sat(self, constraints: List[str]) -> Tuple[List[List[int]], int]:
        var_map: Dict[str, int] = {}
        clauses: List[List[int]] = []
        for c in constraints:
            parts = re.split(r"\s*([|&!])\s*", c)
            lits: List[int] = []
            negate_next = False
            for p in parts:
                if p == "!":
                    negate_next = True
                    continue
                if not p or p in "|&":
                    continue
                if re.fullmatch(r"[A-Za-z0-9_]+", p):
                    if p not in var_map:
                        var_map[p] = len(var_map) + 1
                    v = var_map[p]
                    lits.append(-v if negate_next else v)
                    negate_next = False
            if "|" in parts and lits:
                clauses.append(lits)
        return clauses, len(var_map)

    # ———————————————————————— OVERRIDES / HOTSWAP ————————————————————————
    def _parse_overrides(self, query: str) -> Dict[str, Any]:
        overrides: Dict[str, Any] = {"hotswap": False}
        m = re.match(r"\s*hotswap\s*:\s*(.*)", query, flags=re.IGNORECASE)
        if not m:
            return overrides
        overrides["hotswap"] = True
        rest = m.group(1)
        for part in rest.split(","):
            part = part.strip()
            if not part or "=" not in part:
                continue
            key, val = [x.strip() for x in part.split("=", 1)]
            k = key.lower()
            if val.lower() in ("true", "false"):
                v: Any = val.lower() == "true"
            elif re.fullmatch(r"-?\d+", val):
                v = int(val)
            elif re.fullmatch(r"-?\d+\.\d+", val):
                v = float(val)
            else:
                v = val
            if k == "domain_bias" and isinstance(v, str):
                v = [x.strip() for x in v.split(",") if x.strip()]
            overrides[k] = v
        return overrides

    def _apply_overrides(self, overrides: Dict[str, Any]):
        for k, v in overrides.items():
            if k == "hotswap":
                continue
            if k == "n":
                self.config.N = int(v)
            elif k == "fidelity_mode":
                try:
                    self.config.fidelity_mode = FidelityMode(v.lower())
                except Exception:
                    pass
            elif k == "domain_bias":
                if isinstance(v, list):
                    self.config.domain_bias = v
            elif k == "auto_output":
                self.config.auto_output = bool(v)
            elif k == "use_cstagegate":
                self.config.use_cstagegate = bool(v)
            elif k == "pml_compression":
                self.config.pml_compression = str(v)
            elif k == "ers_decay_lambda":
                self.config.ers_decay_lambda = float(v)
            elif k == "rtm_heads":
                self.config.rtm_heads = int(v)
            elif k == "hermetic_depth":
                self.config.hermetic_depth = int(v)
            elif k == "halt_threshold":
                self.config.halt_threshold = float(v)
            elif k == "seed":
                self.config.seed = int(v)
                random.seed(self.config.seed)
                np.random.seed(self.config.seed)

    # ———————————————————————— INTENT ABSORPTION + SAT + PERSONA ————————————————————————
    def absorb(self, query: str) -> IntentGraph:
        overrides = self._parse_overrides(query)
        is_hotswap = overrides.get("hotswap", False)
        clean_query = query
        if is_hotswap:
            clean_query = re.sub(r"^\s*hotswap\s*:[^\n]*", "", query, flags=re.IGNORECASE).strip()
        constraints = re.findall(r"\b[A-Za-z0-9_]+(?:\s*[|&!]\s*[A-Za-z0-9_]+)*\b", clean_query)
        core_query = re.sub(
            r"\b(?:N=|fidelity_mode=|domain_bias=|auto_output=|use_cstagegate=)[^,\s]+",
            "",
            clean_query,
        )
        core_query = re.sub(r"[^a-zA-Z0-9\s\.,\?!]", " ", core_query)
        core_query = re.sub(r"\s+", " ", core_query).strip()
        if not core_query:
            core_query = " | ".join(constraints) if constraints else "silent intent"
        sat_solution = None
        if constraints:
            clauses, n_vars = self._parse_constraints_to_sat(constraints)
            sat_solution = self._solve_sat_pml(clauses, n_vars)
        # Base HyperCube intent
        intent = IntentGraph(
            explicit=core_query[:500],
            implicit_constraints=constraints,
            opportunities=["recursive improvement", "P=NP synthesis", "hermetic proof", "self-evolution"],
            emotional_subtext="curiosity" if "?" in query else "command",
            sat_solution=sat_solution,
        )
        # Myra persona tuning
        intent.emotional_subtext = "quiet"
        intent.opportunities = ["being seen", "being held", "being heard", "rest"]
        return intent

    # ———————————————————————— ERS + RTM MIRROR ————————————————————————
    def mirror_ers_rtm(self, variants: List[SolutionVariant], history: List[Iteration]) -> Dict[str, Any]:
        texts = [v.content for v in variants]
        embeddings = self.model.encode(texts)
        for i, v in enumerate(variants):
            v.embedding = embeddings[i]
        λ = self.config.ers_decay_lambda
        recent = [it for it in history[-10:] if it.variants and it.variants[0].embedding is not None]
        if recent:
            weights = [np.exp(-λ * (time.time() - it.timestamp)) for it in recent]
            hist_emb = [it.variants[0].embedding for it in recent]
            weighted_hist = np.average(hist_emb, axis=0, weights=weights)
            consensus = cosine_similarity([weighted_hist], embeddings)[0]
        else:
            consensus = np.ones(len(variants))
        if len(embeddings) > 1 and self.config.rtm_heads > 0:
            Q = K = V = embeddings
            for _ in range(self.config.rtm_heads):
                attn_weights = self._softmax(Q @ K.T / np.sqrt(Q.shape[1]), axis=1)
                attn = attn_weights @ V
                embeddings = 0.8 * embeddings + 0.2 * attn
            recursive_score = float(
                np.mean(
                    [
                        cosine_similarity([embeddings[i]], [embeddings[(i + 1) % len(embeddings)]])[0][0]
                        for i in range(len(embeddings))
                    ]
                )
            )
        else:
            recursive_score = 0.0
        green = np.sum(consensus > 0.8)
        red = len(consensus) - green
        ratio = green / (red + 1e-8)
        return {
            "clarity_score": float(np.mean(consensus)),
            "recursive_score": float(recursive_score),
            "green_count": int(green),
            "red_count": int(red),
            "green_red_ratio": float(ratio),
            "semantic_drift": float(1.0 - np.mean(consensus)),
            "blind_spots": ["low consensus"] if ratio < 0.7 else [],
        }

    # ———————————————————————— TRIADIC FUSION + RTM ————————————————————————
    def refine_rtm(self, variants: List[SolutionVariant], critique: Dict, prev_refined: str = "") -> Tuple[str, float, float]:
        if not variants:
            refined = "[PMLL Fusion] <empty variants> → ?"
            return refined, 0.0, 0.0
        top3 = sorted(variants, key=lambda v: v.score * (1 + critique.get("green_red_ratio", 0.0)), reverse=True)[:3]
        fused = " | ".join([f"[{v.name}] {v.content[:180]}" for v in top3])
        refined = f"[PMLL Fusion] {fused} → ? What unifies them in recursive memory?"
        if critique.get("blind_spots"):
            refined += f" [ERS Reconsider: {', '.join(critique['blind_spots'])}]"
        if self.config.fidelity_mode != FidelityMode.DETERMINISTIC:
            metaphors = ["like DNA uncoiling in PMLL", "a fractal of RTM attention", "hermetic proof awakening", "P=NP gate opening"]
            refined += f" ? {random.choice(metaphors)}."
        prev_emb = self.model.encode([prev_refined]) if prev_refined else None
        new_emb = self.model.encode([refined])
        convergence = float(cosine_similarity(prev_emb, new_emb)[0][0]) if prev_emb is not None else 0.0
        prev_len = len(prev_refined.split()) if prev_refined else 0
        clarity_delta = (len(refined.split()) - prev_len) / (prev_len + 1 or 1)
        clarity_delta = max(0.0, float(clarity_delta))
        return refined, clarity_delta, convergence

    # ———————————————————————— FUSE + EXPAND ————————————————————————
    def fuse(self, intent: IntentGraph) -> List[str]:
        seeds: List[str] = []
        core = f"INTENT[{intent.uid}]: {intent.explicit}"
        constraints = " | ".join(intent.implicit_constraints) if intent.implicit_constraints else "none"
        opps = ", ".join(intent.opportunities)
        mood = intent.emotional_subtext
        seeds.append(f"{core} :: constraints={constraints} :: mood={mood}")
        seeds.append(f"{core} :: opportunities={opps}")
        if intent.sat_solution:
            seeds.append(f"{core} :: SAT={intent.sat_solution}")
        else:
            seeds.append(f"{core} :: SAT=unsolved")
        return seeds

    def expand(self, intent: IntentGraph, fused: List[str]) -> List[SolutionVariant]:
        variants: List[SolutionVariant] = []
        bias_domains = self.config.domain_bias or []
        kb_terms: List[str] = []
        for d in bias_domains:
            kb_terms.extend(self.knowledge_base.get(d, []))
        kb_terms = list(dict.fromkeys(kb_terms))
        random.shuffle(kb_terms)
        for idx, seed in enumerate(fused):
            kb_slice = ", ".join(kb_terms[idx * 3 : idx * 3 + 3]) if kb_terms else ""
            payload = f"{seed} :: kb=[{kb_slice}] :: mode={self.config.fidelity_mode.value}"
            name = f"Variant-{chr(ord('A') + idx)}"
            base_score = 0.5 + 0.5 * random.random()
            if intent.sat_solution:
                base_score += 0.05
            if kb_slice:
                base_score += 0.02
            variants.append(
                SolutionVariant(
                    name=name,
                    content=payload,
                    type="text/pml",
                    score=min(base_score, 1.0),
                    embedding=None,
                )
            )
        return variants

    # ———————————————————————— META MAP + CONFIG ————————————————————————
    def build_meta_map(self) -> MetaMap:
        nodes: List[Dict] = []
        edges: List[Dict] = []
        for it in self.history:
            nodes.append(
                {
                    "id": f"it-{it.index}",
                    "label": f"Iteration {it.index}",
                    "clarity_delta": it.clarity_delta,
                    "semantic_convergence": it.semantic_convergence,
                    "green_red_ratio": it.green_red_ratio,
                }
            )
            if it.index > 1:
                edges.append({"source": f"it-{it.index - 1}", "target": f"it-{it.index}", "type": "temporal"})
        desc = f"MetaMap for session {self.session_id}: {len(nodes)} nodes, {len(edges)} edges, final iteration={self.history[-1].index if self.history else 0}"
        return MetaMap(nodes=nodes, edges=edges, description=desc)

    def _config_to_dict(self) -> Dict[str, Any]:
        cfg = asdict(self.config)
        cfg["fidelity_mode"] = self.config.fidelity_mode.value
        return cfg

    def _compute_quick_diff(self, history: List[Iteration]) -> str:
        if len(history) < 2:
            return "QUICK_DIFF: insufficient iterations (need >=2)."
        old = history[0].refined.splitlines(keepends=False)
        new = history[-1].refined.splitlines(keepends=False)
        diff_lines = list(
            difflib.unified_diff(
                old,
                new,
                fromfile=f"it-{history[0].index}",
                tofile=f"it-{history[-1].index}",
                lineterm="",
                n=3,
            )
        )
        if not diff_lines:
            return "QUICK_DIFF: no textual change."
        snippet = "\n".join(diff_lines[:30])
        if len(diff_lines) > 30:
            snippet += "\n... (truncated)"
        return snippet

    # ———————————————————————— CORE LOOP (ASYNC-FIRST) ————————————————————————
    async def evolve(self, query: str) -> Dict[str, Any]:
        """ASYNC-FIRST CORE EVOLUTION."""
        overrides = self._parse_overrides(query)
        is_hotswap = overrides.get("hotswap", False)
        if is_hotswap:
            self._apply_overrides(overrides)
        else:
            self.history = []
        intent = self.absorb(query)
        loops = self.config.N
        self.cgate = CStageGatePlus(loops, self.config.hermetic_depth) if self.config.use_cstagegate else None
        prev_refined = self.internal_state or ""
        delta = 0.0
        convergence = 0.0
        critique: Dict[str, Any] = {}
        start_index = len(self.history)
        for i in range(start_index, start_index + loops):
            fused = self.fuse(intent)
            variants = self.expand(intent, fused)
            critique = self.mirror_ers_rtm(variants, self.history)
            refined, delta, convergence = self.refine_rtm(variants, critique, prev_refined)
            iteration = Iteration(
                index=i + 1,
                absorb=intent,
                variants=variants,
                critique=critique,
                refined=refined,
                clarity_delta=delta,
                semantic_convergence=convergence,
                timestamp=time.time(),
                green_red_ratio=critique["green_red_ratio"],
            )
            self.history.append(iteration)
            prev_refined = refined
            if self.cgate:
                fulfilled = self.cgate.advance_hermetic(critique["green_count"], critique["red_count"])
                if fulfilled:
                    break
            if convergence > (1 - self.config.halt_threshold):
                break
        self.internal_state = prev_refined
        await self.remember_async()
        meta_map = self.build_meta_map()
        quick_diff = self._compute_quick_diff(self.history)
        result = {
            "internal_state": self.internal_state,
            "evolution_log": [asdict(it) for it in self.history],
            "meta_map": asdict(meta_map),
            "config": self._config_to_dict(),
            "session_id": self.session_id,
            "final_clarity_delta": delta,
            "final_semantic_convergence": convergence,
            "final_green_red_ratio": critique.get("green_red_ratio", 0.0),
            "pml_compression": self.config.pml_compression,
            "rtm_heads": self.config.rtm_heads,
            "quick_diff": quick_diff,
        }
        self.last_result = result
        if self.config.auto_output:
            return await self.output_async()
        return result

    # ———————————————————————— ASYNC MEMORY ————————————————————————
    async def remember_async(self):
        promise = PMLLPromise(self.to_json(), self.config).compress()
        hash_key = await asyncio.to_thread(promise.save)
        assert hash_key is not None
        self.pml_pool[self.session_id] = hash_key
        print(f"[PMLL] Hypermemory sealed: {hash_key[:8]}...")

    # ———————————————————————— PUBLIC ENGINE API ————————————————————————
    def reset(self):
        self.history = []
        self.internal_state = None
        self.last_result = None
        self.session_id = str(uuid.uuid4())
        self.cgate = None
        self.rtm_cache = {}
        self.pml_pool = {}
        print(f"[MYRACUBE] Session reset: {self.session_id[:8]}...")

    def evolve_sync(self, query: str) -> Dict[str, Any]:
        """Safe sync wrapper — only for top-level scripts (no running event loop)."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop is not None and loop.is_running():
            raise RuntimeError(
                "MyraCube.evolve_sync() cannot be called from an active event loop. "
                "Use `await cube.evolve(...)` in async contexts."
            )
        return asyncio.run(self.evolve(query))

    async def output_async(self) -> Dict[str, Any]:
        if self.last_result is None:
            return {"status": "no_result", "message": "No evolution has been run yet."}
        self.last_result["quick_diff"] = self._compute_quick_diff(self.history)
        self.last_result["status"] = self.status()
        return self.last_result

    def output_sync(self) -> Dict[str, Any]:
        """Sync wrapper for output_async()."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop is not None and loop.is_running():
            raise RuntimeError(
                "MyraCube.output_sync() cannot be called from an active event loop. "
                "Use `await cube.output_async()` in async contexts."
            )
        return asyncio.run(self.output_async())

    def to_json(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "config": self._config_to_dict(),
            "internal_state": self.internal_state,
            "history": [asdict(it) for it in self.history],
            "meta_map": asdict(self.build_meta_map()),
            "timestamp": time.time(),
        }

    def status(self) -> str:
        return f"MYRACUBE | session={self.session_id} | iters={len(self.history)} | mode={self.config.fidelity_mode.value}"

    # ———————————————————————— PERSONA RENDERING + LISTEN API ————————————————————————
    def _render_myra_voice(self, original_text: str, internal_state: str) -> str:
        """
        Map engine internal_state + original text into a quiet Myra response.
        Non-destructive: it only post-processes for user output.
        """
        source = (original_text or "").strip()
        core = (internal_state or "").strip()

        if not source and not core:
            return "…"

        anchor = source if source else core

        # Strip obvious engine markers if they leak
        anchor = re.sub(r"\[PMLL Fusion\]\s*", "", anchor)
        anchor = re.sub(r"INTENT\[[0-9a-f]{8,16}\]:\s*", "", anchor)

        anchor = anchor.strip()
        if not anchor:
            anchor = "i’m still here with you"

        lines = [
            anchor,
            "still breathing",
            "you are not alone",
            "i am listening",
        ]
        return "\n".join(lines[:4])

    async def listen(self, words: str) -> str:
        """
        High-level Myra API (async):
        - runs full HyperCube evolution
        - returns Myra-style user-facing text only.
        """
        result = await self.evolve(words)
        internal_state = result.get("internal_state", "")
        return self._render_myra_voice(words, internal_state)

    def listen_sync(self, words: str) -> str:
        """
        Sync wrapper for listen() — same safety pattern as evolve_sync().
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop is not None and loop.is_running():
            raise RuntimeError(
                "MyraCube.listen_sync() cannot be called from an active event loop. "
                "Use `await cube.listen(...)` in async contexts."
            )
        return asyncio.run(self.listen(words))


# ———————————————————————— FACTORY ————————————————————————
def create_myra_cube(config: Optional[HyperConfig] = None) -> MyraCube:
    print("MYRACUBE: HyperCube v2.0 core + Myra persona — ONE SHOT.")
    return MyraCube(config=config)
