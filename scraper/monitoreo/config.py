"""Carga y validación de ``config/monitoreo.yaml`` (Anexo I, punto 3).

Se usan dataclasses simples y validación explícita: esta etapa no depende de
pydantic ni de FastAPI para poder correr con solo ``pyyaml`` instalado.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

MODOS_VALIDOS = {"word", "phrase", "prefix", "substring"}
TIPOS_CANAL_VALIDOS = {"wp_rest", "rss", "sitemap", "html"}

RUTA_CONFIG_POR_DEFECTO = Path(__file__).resolve().parents[1] / "config" / "monitoreo.yaml"


class ConfigInvalida(ValueError):
    """El archivo de configuración tiene un error de forma o de contenido."""


def _requerir(d: dict[str, Any], clave: str, ctx: str) -> Any:
    if not isinstance(d, dict) or clave not in d:
        raise ConfigInvalida(f"{ctx}: falta la clave obligatoria '{clave}'")
    return d[clave]


@dataclass(frozen=True)
class TerminoCfg:
    id: str
    patron: str
    modo: str = "word"
    etiqueta_especial: str | None = None
    coincide_directo_si_frase: str | None = None
    requiere_contexto: bool = False
    contexto_any: tuple[str, ...] = ()

    @staticmethod
    def desde_dict(d: dict[str, Any], ctx: str) -> "TerminoCfg":
        tid = _requerir(d, "id", ctx)
        modo = d.get("modo", "word")
        if modo not in MODOS_VALIDOS:
            raise ConfigInvalida(
                f"{ctx} ({tid}): modo '{modo}' no válido; use uno de {sorted(MODOS_VALIDOS)}"
            )
        requiere_contexto = bool(d.get("requiere_contexto", False))
        contexto_any = tuple(d.get("contexto_any", ()) or ())
        if requiere_contexto and not contexto_any:
            raise ConfigInvalida(
                f"{ctx} ({tid}): 'requiere_contexto' es true pero 'contexto_any' está vacío"
            )
        return TerminoCfg(
            id=str(tid),
            patron=str(_requerir(d, "patron", f"{ctx} ({tid})")),
            modo=modo,
            etiqueta_especial=d.get("etiqueta_especial"),
            coincide_directo_si_frase=d.get("coincide_directo_si_frase"),
            requiere_contexto=requiere_contexto,
            contexto_any=contexto_any,
        )


@dataclass(frozen=True)
class NivelCfg:
    clave: str
    etiqueta: str
    terminos: tuple[TerminoCfg, ...]


@dataclass(frozen=True)
class CanalCfg:
    tipo: str
    url: str


@dataclass(frozen=True)
class MedioCfg:
    id: str
    nombre: str
    dominio: str
    motor: str
    canales: tuple[CanalCfg, ...]


@dataclass(frozen=True)
class IngestaCfg:
    intervalo_minutos: int = 20
    user_agent: str = "MonitoreoPrensaMoron/1.0"
    timeout_segundos: int = 15


@dataclass(frozen=True)
class ConfigMonitoreo:
    compuerta: tuple[str, ...]
    niveles: tuple[NivelCfg, ...]
    context_window_words: int = 40
    medios: tuple[MedioCfg, ...] = ()
    ingesta: IngestaCfg = field(default_factory=IngestaCfg)
    # Si es False, alcanza con pasar la compuerta: los niveles solo etiquetan.
    exigir_termino: bool = True

    def nivel(self, clave: str) -> NivelCfg:
        for n in self.niveles:
            if n.clave == clave:
                return n
        raise KeyError(clave)

    def medio(self, medio_id: str) -> MedioCfg:
        for m in self.medios:
            if m.id == medio_id:
                return m
        raise KeyError(medio_id)

    # ------------------------------------------------------------------
    @classmethod
    def desde_yaml(cls, ruta: str | Path | None = None) -> "ConfigMonitoreo":
        ruta = Path(ruta) if ruta is not None else RUTA_CONFIG_POR_DEFECTO
        if not ruta.is_file():
            raise ConfigInvalida(f"No se encuentra el archivo de configuración: {ruta}")
        datos = yaml.safe_load(ruta.read_text(encoding="utf-8"))
        if not isinstance(datos, dict):
            raise ConfigInvalida(f"{ruta}: el contenido raíz debe ser un mapa YAML")
        return cls.desde_dict(datos, ctx=str(ruta))

    @classmethod
    def desde_dict(cls, datos: dict[str, Any], ctx: str = "config") -> "ConfigMonitoreo":
        # compuerta
        compuerta = _requerir(datos, "compuerta", ctx)
        if not isinstance(compuerta, list) or not compuerta:
            raise ConfigInvalida(f"{ctx}: 'compuerta' debe ser una lista no vacía")
        compuerta = tuple(str(x) for x in compuerta)

        # matching
        matching = datos.get("matching") or {}
        context_window_words = int(matching.get("context_window_words", 40))
        if context_window_words < 1:
            raise ConfigInvalida(f"{ctx}: 'context_window_words' debe ser >= 1")

        # niveles
        niveles_raw = _requerir(datos, "niveles", ctx)
        if not isinstance(niveles_raw, dict) or not niveles_raw:
            raise ConfigInvalida(f"{ctx}: 'niveles' debe ser un mapa no vacío")
        niveles: list[NivelCfg] = []
        vistos: set[str] = set()
        for clave, cuerpo in niveles_raw.items():
            ctx_n = f"{ctx}.niveles.{clave}"
            etiqueta = str(_requerir(cuerpo, "etiqueta", ctx_n))
            terminos_raw = _requerir(cuerpo, "terminos", ctx_n)
            if not isinstance(terminos_raw, list) or not terminos_raw:
                raise ConfigInvalida(f"{ctx_n}: 'terminos' debe ser una lista no vacía")
            terminos: list[TerminoCfg] = []
            for t in terminos_raw:
                term = TerminoCfg.desde_dict(t, ctx_n)
                if term.id in vistos:
                    raise ConfigInvalida(f"{ctx}: id de término duplicado '{term.id}'")
                vistos.add(term.id)
                terminos.append(term)
            niveles.append(NivelCfg(clave=str(clave), etiqueta=etiqueta, terminos=tuple(terminos)))

        # medios
        medios: list[MedioCfg] = []
        for m in datos.get("medios", []) or []:
            ctx_m = f"{ctx}.medios"
            mid = str(_requerir(m, "id", ctx_m))
            canales_raw = _requerir(m, "canales", f"{ctx_m} ({mid})")
            if not isinstance(canales_raw, list) or not canales_raw:
                raise ConfigInvalida(f"{ctx_m} ({mid}): 'canales' debe ser una lista no vacía")
            canales: list[CanalCfg] = []
            for c in canales_raw:
                tipo = str(_requerir(c, "tipo", f"{ctx_m} ({mid})"))
                if tipo not in TIPOS_CANAL_VALIDOS:
                    raise ConfigInvalida(
                        f"{ctx_m} ({mid}): tipo de canal '{tipo}' no válido; "
                        f"use uno de {sorted(TIPOS_CANAL_VALIDOS)}"
                    )
                canales.append(CanalCfg(tipo=tipo, url=str(_requerir(c, "url", f"{ctx_m} ({mid})"))))
            medios.append(
                MedioCfg(
                    id=mid,
                    nombre=str(_requerir(m, "nombre", f"{ctx_m} ({mid})")),
                    dominio=str(_requerir(m, "dominio", f"{ctx_m} ({mid})")),
                    motor=str(m.get("motor", "por_verificar")),
                    canales=tuple(canales),
                )
            )

        # ingesta
        ing = datos.get("ingesta") or {}
        ingesta = IngestaCfg(
            intervalo_minutos=int(ing.get("intervalo_minutos", 20)),
            user_agent=str(ing.get("user_agent", "MonitoreoPrensaMoron/1.0")),
            timeout_segundos=int(ing.get("timeout_segundos", 15)),
        )

        return cls(
            compuerta=compuerta,
            niveles=tuple(niveles),
            context_window_words=context_window_words,
            medios=tuple(medios),
            ingesta=ingesta,
            exigir_termino=bool(datos.get("exigir_termino", True)),
        )
