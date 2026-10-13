"""Auditoria pós-edição: compara o texto antes e depois da revisão.

Revisão muda palavras, não conteúdo. A auditoria verifica de forma determinística (stdlib, sem
rede) que nada que carrega conteúdo se perdeu ou foi acrescentado:

  entrada                  - os dois textos não vazios; texto sem mudança é resultado válido
  valores_sensiveis        - multiconjunto: dispositivos legais, datas, números de processo,
                             números e valores, citações, campos a preencher; falta ou sobra = BLOQUEIO
  perfil_deontico          - quantas obrigações, proibições, permissões e recomendações antes e
                             depois; molduras de discurso ("vale ressaltar") não contam
  certeza                  - "provavelmente" / "preliminarmente" removidos sem rastro de incerteza
                             = BLOQUEIO; desbastar hedging empilhado é permitido
  vestigios_de_ferramenta  - campos não preenchidos e fórmulas de chat na saída = texto não pronto
  termos_protegidos        - termos jurídicos, termos definidos no texto (inclusive em CAIXA ALTA)
                             e termos passados por parâmetro; trocar por "sinônimo" = BLOQUEIO
  limite_de_corte          - perda de palavras acima do limite (padrão 30%) = BLOQUEIO; o limite é
                             teto, não meta

Resultado OK / ALERTA / BLOQUEIO com denominador completo (toda verificação aparece, inclusive as
aprovadas). Código de saída: 0 OK, 10 ALERTA, 20 BLOQUEIO, 2 chamada errada.

Uso:  python auditoria_pos_edicao.py ANTES.txt DEPOIS.txt [--corte-maximo 0.3]
          [--protegidos "termo1;termo2"] [--json]
"""
import argparse
import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

VERIFICACOES = ("entrada", "valores_sensiveis", "perfil_deontico", "certeza", "vestigios_de_ferramenta",
                "termos_protegidos", "limite_de_corte")
NIVEL = {"OK": 0, "ALERTA": 1, "BLOQUEIO": 2}
SAIDA = {"OK": 0, "ALERTA": 10, "BLOQUEIO": 20}
TEXTO_CURTO = 40  # abaixo disso o limite de corte é indicativo (ALERTA), não rígido

MESES = {m: i for i, m in enumerate(
    ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro",
     "outubro", "novembro", "dezembro"], start=1)}
L = r"[A-Za-zÀ-ÖØ-öø-ÿ]"
IB = rf"(?<!{L})"  # limite de palavra à esquerda
FB = rf"(?!{L})"   # limite de palavra à direita

# --- normalização -------------------------------------------------------------------------

def norm(t: str) -> str:
    t = unicodedata.normalize("NFC", t)
    t = re.sub(r"[‐-―−]", "-", t)
    t = re.sub(r"[   \t\r\n ]+", " ", t)
    return t.strip()


def palavras(t: str) -> list:
    return re.findall(r"\w+", t)

# --- valores sensíveis --------------------------------------------------------------------

RE_CITACAO = re.compile(r"[\"“«]([^\"“”«»]{2,400})[\"”»]")
RE_MARCADOR = re.compile(r"\[a completar:[^\]\n]*\]", re.I)  # marcador do skill: não é valor, mas o texto não está pronto
# campo a preencher tem letra: nota "[1]" e "[2026]" não são campos
RE_CAMPO = re.compile(r"\[(?=[^\]\n]*[A-Za-zÀ-ÿ])[^\]\n]{1,60}\]|\{\{[^}\n]{1,60}\}\}|<[^<>\n]{1,40}>")
ORD = r"[ºª°o]?"
RE_DISP = re.compile(
    rf"{IB}(?:art\.|artigo|arts\.|§+|inciso|inc\.|alínea|al\.)\s*(?:\d[\d.]*{ORD}(?:-[A-Z])?|[IVXLC]+{FB}|[a-z]\){0}|[a-z]{FB})"
    rf"(?:\s*,?\s*(?:§+\s*\d+{ORD}|inciso\s+[IVXLC]+{FB}|inc\.\s*[IVXLC]+{FB}|alínea\s+[a-z]{FB}|caput|"
    rf"parágrafo\s+único|[IVXLC]+{FB}))*", re.I)
RE_PROC = re.compile(r"\b\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}\b"
                     r"|\b(?:REsp|AREsp|RE|ARE|ADI|ADC|ADPF|HC|MS|AgInt|AgRg|RR|AIRR)\s+(?:n[ºo°.]\s*)?[\d.]+(?:/[A-Z]{2})?")
RE_DATA_EXT = re.compile(rf"{IB}(\d{{1,2}})º?\s+de\s+({'|'.join(MESES)})\s+de\s+(\d{{4}}){FB}", re.I)
RE_DATA_NUM = re.compile(r"(?<!\d)(\d{1,2})[./](\d{1,2})[./](\d{4})(?!\d)")
RE_DATA_ISO = re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)")
RE_NUM = re.compile(r"(?<![\d,])\d{1,3}(?:\.\d{3})+(?:,\d+)?(?!\d)|(?<![\d,.])\d+(?:,\d+)?(?!\d)")


def _mascarar(t, rx, achados, rotulo, canon=lambda m: norm(m.group(0))):
    def sub(m):
        achados.append((rotulo, canon(m)))
        return " \u0000 "
    return rx.sub(sub, t)


def _disp_canon(m):
    s = re.sub(r"\s+", "", m.group(0).lower())
    for a, b in (("artigo", "art."), ("arts.", "art."), ("inc.", "inciso"), ("al.", "alínea"),
                 ("º", "o"), ("ª", "o"), ("°", "o"), (",", "")):
        s = s.replace(a, b)
    return s


def valores(t: str) -> Counter:
    """Multiconjunto de valores que a revisão não pode perder nem acrescentar."""
    t = RE_MARCADOR.sub(" ", norm(t))
    ach = []
    t = _mascarar(t, RE_CITACAO, ach, "citação", lambda m: norm(m.group(1)))
    t = _mascarar(t, RE_CAMPO, ach, "campo")
    t = _mascarar(t, RE_PROC, ach, "processo", lambda m: re.sub(r"\s+", " ", m.group(0)))
    t = _mascarar(t, RE_DISP, ach, "dispositivo", _disp_canon)
    t = _mascarar(t, RE_DATA_EXT, ach, "data", lambda m: "%s-%02d-%02d" % (
        m.group(3), MESES[m.group(2).lower()], int(m.group(1))))
    t = _mascarar(t, RE_DATA_NUM, ach, "data", lambda m: "%s-%02d-%02d" % (m.group(3), int(m.group(2)), int(m.group(1))))
    t = _mascarar(t, RE_DATA_ISO, ach, "data", lambda m: m.group(0))
    _mascarar(t, RE_NUM, ach, "número", lambda m: m.group(0).replace(".", ""))
    return Counter(ach)

# --- perfil deôntico ----------------------------------------------------------------------

MOLDURAS = [r"vale\s+(?:a\s+pena\s+)?(?:ressaltar|destacar|lembrar|notar|mencionar|dizer|frisar)",
            r"cabe\s+(?:ressaltar|destacar|salientar|lembrar|mencionar|observar|frisar)",
            r"é\s+(?:importante|preciso|necessário|válido|interessante)\s+(?:destacar|ressaltar|lembrar|notar|"
            r"mencionar|observar|salientar|dizer|frisar)",
            r"(?:deve|pode)-se\s+(?:ressaltar|destacar|notar|observar|lembrar|dizer|afirmar)"]
NEG = {
    "permissao": [r"não\s+precisa[m]?", r"não\s+é\s+(?:obrigatório|necessário|preciso)", r"não\s+(?:é|está|são|estão)\s+obrigad[oa]s?",
                  r"não\s+tem\s+(?:a\s+)?obrigação"],
    "recomendacao": [r"não\s+deveria[m]?"],
    "proibicao": [r"não\s+(?:pode|podem|poderá|poderão|deve|devem|deverá|deverão)",
                  r"não\s+(?:é|está|são|estão)\s+(?:permitid|autorizad)[oa]s?", r"não\s+t[eê]m?\s+(?:o\s+)?direito"],
}
POS = {
    "proibicao": [r"(?:é|fica|são|ficam)\s+vedad[oa]s?", r"veda-se", r"(?:é|são)\s+proibid[oa]s?", r"proíbe-se", r"é\s+defeso"],
    "obrigacao": [r"deve[m]?", r"deverá", r"deverão", r"t[eê]m?\s+(?:que|de)", r"(?:é|fica|são|ficam)\s+obrigad[oa]s?",
                  r"obriga[m]?-se", r"é\s+obrigatório", r"precisa[m]?"],
    "permissao": [r"pode[m]?", r"poderá", r"poderão", r"(?:é|fica|são)\s+(?:permitid|facultad)[oa]s?", r"faculta-se",
                  r"t[eê]m?\s+(?:o\s+)?direito"],
    "recomendacao": [r"deveria[m]?", r"recomenda-se", r"é\s+(?:recomendável|aconselhável)", r"recomendamos"],
}


def _rx(padroes):
    return re.compile(IB + "(?:" + "|".join(padroes) + ")" + FB, re.I)


def perfil_deontico(t: str) -> dict:
    t = _rx(MOLDURAS).sub(" ", norm(t))
    out = Counter({k: 0 for k in ("obrigacao", "proibicao", "permissao", "recomendacao")})
    for grupo in (NEG, POS):
        for cat, pads in grupo.items():
            rx = _rx(pads)
            out[cat] += len(rx.findall(t))
            t = rx.sub(" ", t)
    return dict(out)

# --- certeza ------------------------------------------------------------------------------

RE_INCERTO = re.compile(IB + "(?:" + "|".join([
    r"provavelmente", r"possivelmente", r"talvez", r"preliminar\w*", r"provisori\w*", r"provisóri\w*",
    r"estimad[oa]s?", r"aproximadamente", r"cerca\s+de", r"em\s+tese", r"ao\s+que\s+tudo\s+indica",
    r"aparentemente", r"parece[m]?", r"ainda\s+não\s+(?:se\s+sabe|está\s+claro|foi\s+definid\w+|há\s+definição)",
    r"não\s+está\s+claro", r"potencialmente", r"eventualmente", r"é\s+possível\s+que",
]) + ")" + FB, re.I)
RE_PODE = re.compile(IB + r"(?:pode[m]?|poderá|poderão|poderia[m]?|possa[m]?)" + FB, re.I)


def incerteza(t: str) -> int:
    return len(RE_INCERTO.findall(norm(t)))

# --- vestígios de ferramenta --------------------------------------------------------------

INICIO = re.compile(r"^\s*(?:claro[!,.]|com\s+certeza[!,.]|aqui\s+est(?:á|ão)|segue[m]?\s+(?:abaixo|a\s|o\s)|"
                    r"ótima\s+pergunta|perfeito[!,.])", re.I)
FORMULAS = re.compile(r"espero\s+que\s+(?:isso\s+|isto\s+)?(?:ajude|tenha\s+ajudado|seja\s+útil)|"
                      r"se\s+precisar\s+de\s+(?:ajustes|mais\s+alguma|algo\s+mais)|é\s+só\s+(?:avisar|pedir|falar)|"
                      r"gostaria\s+que\s+eu|quer\s+que\s+eu|como\s+(?:um\s+)?modelo\s+de\s+linguagem|"
                      r"como\s+(?:uma\s+)?(?:IA|inteligência\s+artificial)\b", re.I)
OFERTA = re.compile(r"você\s+pode\s+(?:facilmente\s+)?(?:ajustar|adaptar|personalizar|editar|modificar|copiar|colar|preencher)|"
                    r"posso\s+(?:também\s+|ainda\s+)?(?:preparar|elaborar|redigir|ajustar|adaptar|resumir|traduzir|ajudar|criar)", re.I)
AVISO = re.compile(r"não\s+constitui\s+(?:aconselhamento|consultoria|parecer|orientação)\s+jurídic[oa]", re.I)


def sem_envelope(t: str) -> str:
    """Texto sem as frases de envelope do chat ("Aqui está...", "Você pode ajustar...", "Espero que ajude").

    Modais e termos do envelope não são conteúdo do documento: removê-los não muda norma nem
    terminologia, então não pode bloquear o perfil.
    """
    frases = re.split(r"(?<=[.!?:])\s+", norm(t))
    return " ".join(f for f in frases if not (INICIO.match(f) or FORMULAS.search(f) or OFERTA.search(f)))

# --- termos protegidos --------------------------------------------------------------------

# Pares que um leigo toma por sinônimos e o direito não. Chave = nome, valor = radical.
TERMOS = {
    "arras/sinal": r"arras|sina(?:l|is)", "adiantamento": r"adiantamentos?",
    "rescisão": r"rescis(?:ão|ões)|rescindi\w*", "resolução": r"resolução\s+(?:do|da|de)\s+contrato",
    "resilição": r"resilição|resili\w*", "denúncia": r"denúncia", "distrato": r"distratos?",
    "garantia": r"garantias?", "vício": r"vícios?\s+(?:redibitóri\w+|ocult\w+|do\s+produto)",
    "nulidade": r"nulidade\w*|nul[oa]s?", "anulabilidade": r"anulabilidade|anuláve\w*",
    "multa": r"multas?", "cláusula penal": r"cláusulas?\s+pena\w*", "indenização": r"indeniza\w*",
    "prescrição": r"prescri\w*", "decadência": r"decad\w*", "compensação": r"compensação\s+de\s+crédito\w*",
    "cessão de crédito": r"cess(?:ão|ões)\s+de\s+crédito\w*", "procuração": r"procuraç\w*", "mandato": r"mandatos?",
    "fiança": r"fianç\w*", "aval": r"aval\b|avalista\w*", "penhor": r"penhor\w*", "hipoteca": r"hipotec\w*",
    "sentença": r"sentenças?", "acórdão": r"acórd(?:ão|ãos)", "apelação": r"apelaç\w*", "agravo": r"agravos?",
    "recurso especial": r"recursos?\s+especia\w*", "locação": r"locaç\w*", "comodato": r"comodatos?",
    "arrendamento": r"arrendament\w*", "juros": r"juros",
}
_TERMO_RX = {k: re.compile(IB + "(?:" + v + ")" + FB, re.I) for k, v in TERMOS.items()}
RE_DEF = re.compile(
    r"\((?:doravante\s+|adiante\s+)?(?:denominad[oa]s?\s+|designad[oa]s?\s+|simplesmente\s+)?[\"“«]([^\"“”«»]{2,40})[\"”»]\)"
    r"|(?:doravante|adiante)(?:\s+(?:denominad|designad|chamad)[oa]s?)?(?:\s+simplesmente)?\s+[\"“«]([^\"“”«»]{2,40})[\"”»]"
    r"|[\"“«]([^\"“”«»]{2,40})[\"”»]\s+(?:significa|designa|refere-se)", re.I)
RE_CAIXA_ALTA = re.compile(r"(?<![A-Za-zÀ-ÿ])[A-ZÀ-Ö]{6,}(?![A-Za-zÀ-ÿ])")


def termos_definidos(t: str) -> list:
    t = norm(t)
    out = []
    for m in RE_DEF.finditer(t):
        termo = next(g for g in m.groups() if g).strip()
        if termo not in out:
            out.append(termo)
    for termo, n in Counter(RE_CAIXA_ALTA.findall(t)).items():
        if n >= 2 and termo not in out:  # CONTRATANTE, LOCATÁRIO: termo definido usual em contrato brasileiro
            out.append(termo)
    return out


def _contar_literal(t: str, termo: str) -> int:
    return len(re.findall(IB + re.escape(termo) + FB, t))

# --- auditoria ----------------------------------------------------------------------------

def _v(nome, status, detalhes):
    return {"nome": nome, "status": status, "detalhes": detalhes}


def auditar(antes: str, depois: str, corte_maximo: float = 0.30, protegidos=()) -> dict:
    a, b = norm(antes or ""), norm(depois or "")
    vs = []
    if not a or not b:
        vs.append(_v("entrada", "BLOQUEIO", "texto vazio " + ("antes da revisão" if not a else "depois da revisão")
                     + " - não há o que comparar, e isso não é aprovação"))
        vs += [_v(n, "BLOQUEIO", "não executada: entrada vazia") for n in VERIFICACOES[1:]]
        return {"status": "BLOQUEIO", "sem_mudanca": False, "verificacoes": vs}

    sem_mudanca = a == b
    vs.append(_v("entrada", "OK", "sem mudança - resultado válido quando o texto não precisava de revisão"
                 if sem_mudanca else f"palavras antes: {len(palavras(a))}, depois: {len(palavras(b))}"))

    va, vb = valores(a), valores(b)
    perdeu, ganhou = va - vb, vb - va
    if perdeu or ganhou:
        partes = []
        if perdeu:
            partes.append("sumiu: " + "; ".join(f"{k} {v}" for (k, v) in sorted(perdeu.elements())))
        if ganhou:
            partes.append("apareceu: " + "; ".join(f"{k} {v}" for (k, v) in sorted(ganhou.elements())))
        vs.append(_v("valores_sensiveis", "BLOQUEIO", " | ".join(partes)))
    else:
        vs.append(_v("valores_sensiveis", "OK", f"conferem: {sum(va.values())} valores"))

    ta, tb = sem_envelope(a), sem_envelope(b)  # o envelope do chat não é conteúdo do documento
    pa, pb = perfil_deontico(ta), perfil_deontico(tb)
    dif = {k: (pa[k], pb[k]) for k in pa if pa[k] != pb[k]}
    if dif:
        vs.append(_v("perfil_deontico", "BLOQUEIO", "a força de uma norma mudou: " + ", ".join(
            f"{k} {x}->{y}" for k, (x, y) in dif.items()) + " (confira cada 'pode', 'deve', 'não pode', 'deveria')"))
    else:
        vs.append(_v("perfil_deontico", "OK", ", ".join(f"{k} {v}" for k, v in pa.items())))

    ia, ib = incerteza(ta), incerteza(tb)
    if ia and not ib and not RE_PODE.search(tb):
        vs.append(_v("certeza", "BLOQUEIO", f"marcadores de incerteza {ia}->0: o texto afirma mais do que o original "
                     "('provavelmente', 'preliminarmente' são conteúdo, não enchimento)"))
    elif ib > ia:
        vs.append(_v("certeza", "ALERTA", f"incerteza acrescentada {ia}->{ib} - o original a deixou de fora de propósito?"))
    else:
        vs.append(_v("certeza", "OK", f"marcadores de incerteza {ia}->{ib}"
                     + (" (hedging empilhado desbastado, incerteza mantida)" if ib < ia else "")))

    vest = [m.group(0) for m in RE_MARCADOR.finditer(b)]
    vest += [m.group(0) for m in RE_CAMPO.finditer(RE_MARCADOR.sub(" ", b))]
    vest += [m.group(0).strip() for m in INICIO.finditer(b)]
    vest += [m.group(0) for m in FORMULAS.finditer(b)]
    vest += [m.group(0) for m in OFERTA.finditer(b)]
    if vest:
        vs.append(_v("vestigios_de_ferramenta", "BLOQUEIO", "texto não está pronto para envio: " + "; ".join(vest)
                     + " (quem preenche os campos é uma pessoa - não invente valores; tire as fórmulas de chat)"))
    elif AVISO.search(b) and not AVISO.search(a):
        vs.append(_v("vestigios_de_ferramenta", "ALERTA", "'não constitui aconselhamento jurídico' acrescentado - intencional?"))
    else:
        vs.append(_v("vestigios_de_ferramenta", "OK", "sem campos a preencher e sem fórmulas de chat"))

    bloq, alert = [], []
    for nome, rx in _TERMO_RX.items():
        x, y = len(rx.findall(ta)), len(rx.findall(tb))
        if (x == 0) != (y == 0):
            bloq.append(f"{nome} {x}->{y}")
        elif x != y:
            alert.append(f"{nome} {x}->{y}")
    for termo in list(termos_definidos(a)) + [p for p in protegidos if p]:
        x, y = _contar_literal(ta, termo), _contar_literal(tb, termo)
        if x and not y:
            bloq.append(f'"{termo}" {x}->0')
        elif x != y:
            alert.append(f'"{termo}" {x}->{y}')
    if bloq:
        vs.append(_v("termos_protegidos", "BLOQUEIO", "um termo sumiu ou apareceu no lugar de outro: "
                     + "; ".join(bloq) + ("; alertas: " + "; ".join(alert) if alert else "")))
    elif alert:
        vs.append(_v("termos_protegidos", "ALERTA", "mudou o número de usos: " + "; ".join(alert)))
    else:
        vs.append(_v("termos_protegidos", "OK", "termos sem mudança"))

    # medido sem o envelope do chat: tirar "Claro! Aqui está..." não é perda, e contá-lo empurra
    # o revisor a manter enchimento só para ficar abaixo do limite
    na, nb = len(palavras(ta)), len(palavras(tb))
    corte = (na - nb) / na if na else 0.0
    if corte > corte_maximo:
        curto = na < TEXTO_CURTO
        vs.append(_v("limite_de_corte", "ALERTA" if curto else "BLOQUEIO",
                     f"corte de {corte:.0%} > limite de {corte_maximo:.0%} - texto mais curto não é a meta"
                     + (f" (texto com menos de {TEXTO_CURTO} palavras: limite indicativo; quem guarda os fatos é"
                        " a verificação de valores)" if curto else "")))
    else:
        vs.append(_v("limite_de_corte", "OK", f"mudança de tamanho {-corte:+.0%} (limite de corte {corte_maximo:.0%})"))

    status = max((k["status"] for k in vs), key=NIVEL.get)
    return {"status": status, "sem_mudanca": sem_mudanca, "verificacoes": vs}


def relatorio(r: dict) -> str:
    n = Counter(k["status"] for k in r["verificacoes"])
    linhas = [f"AUDITORIA PÓS-EDIÇÃO: {r['status']} (verificações {len(r['verificacoes'])}: OK {n['OK']}, "
              f"ALERTA {n['ALERTA']}, BLOQUEIO {n['BLOQUEIO']})"]
    linhas += [f"  [{k['status']}] {k['nome']}: {k['detalhes']}" for k in r["verificacoes"]]
    return "\n".join(linhas)


def main(argv=None) -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    p = argparse.ArgumentParser(description="Auditoria pós-edição (humanizer-pt)")
    p.add_argument("antes")
    p.add_argument("depois")
    p.add_argument("--corte-maximo", type=float, default=0.30, help="perda máxima de palavras (0-1), padrão 0.30")
    p.add_argument("--protegidos", default="", help="termos protegidos literalmente, separados por ';'")
    p.add_argument("--json", action="store_true")
    a = p.parse_args(argv)
    r = auditar(Path(a.antes).read_text(encoding="utf-8"), Path(a.depois).read_text(encoding="utf-8"),
                corte_maximo=a.corte_maximo, protegidos=[x.strip() for x in a.protegidos.split(";")])
    print(json.dumps(r, ensure_ascii=False, indent=1) if a.json else relatorio(r))
    return SAIDA[r["status"]]


if __name__ == "__main__":
    sys.exit(main())
