"""Testes da auditoria pós-edição (stdlib unittest).

Rode a partir da pasta do skill:  python -m unittest discover -s tests -v
Casos sintéticos escritos para o fenômeno (data perdida, força da norma alterada), não para a regex.
"""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "auditoria_pos_edicao.py"
sys.path.insert(0, str(SCRIPT.parent))

import auditoria_pos_edicao as A  # noqa: E402

TEXTO = (
    "O prazo para impugnação termina em 15 de março de 2026. O cliente pagará R$ 12.500,00 de "
    "honorários, e o LOCATÁRIO pode rescindir a locação com aviso de 30 dias. "
    "Base: art. 7º, inciso IX, da LGPD e o processo 0001234-56.2024.8.26.0100."
)


def ver(r, nome):
    return next(k for k in r["verificacoes"] if k["nome"] == nome)


class Entrada(unittest.TestCase):
    def test_texto_identico_ok_e_sem_mudanca_e_resultado(self):
        r = A.auditar(TEXTO, TEXTO)
        self.assertEqual(r["status"], "OK")
        self.assertTrue(r["sem_mudanca"])

    def test_saida_vazia_bloqueia(self):
        self.assertEqual(A.auditar(TEXTO, "  \n")["status"], "BLOQUEIO")

    def test_original_vazio_bloqueia(self):
        self.assertEqual(A.auditar("", TEXTO)["status"], "BLOQUEIO")

    def test_denominador_completo_mesmo_quando_ok(self):
        r = A.auditar(TEXTO, TEXTO)
        self.assertEqual({k["nome"] for k in r["verificacoes"]}, set(A.VERIFICACOES))
        self.assertTrue(all(k["status"] == "OK" for k in r["verificacoes"]))


class ValoresSensiveis(unittest.TestCase):
    def test_data_perdida_bloqueia(self):
        saida = TEXTO.replace("15 de março de 2026", "meados de março")
        self.assertEqual(ver(A.auditar(TEXTO, saida), "valores_sensiveis")["status"], "BLOQUEIO")

    def test_data_reformatada_passa(self):
        saida = TEXTO.replace("15 de março de 2026", "15/03/2026")
        self.assertEqual(ver(A.auditar(TEXTO, saida), "valores_sensiveis")["status"], "OK")

    def test_valor_alterado_bloqueia(self):
        saida = TEXTO.replace("R$ 12.500,00", "R$ 12.000,00")
        self.assertEqual(ver(A.auditar(TEXTO, saida), "valores_sensiveis")["status"], "BLOQUEIO")

    def test_espaco_rigido_no_valor_passa(self):
        saida = TEXTO.replace("R$ 12.500,00", "R$ 12.500,00")
        self.assertEqual(ver(A.auditar(TEXTO, saida), "valores_sensiveis")["status"], "OK")

    def test_numero_inventado_bloqueia(self):
        saida = TEXTO + " Isso reduz o processo em 30%."
        self.assertEqual(ver(A.auditar(TEXTO, saida), "valores_sensiveis")["status"], "BLOQUEIO")

    def test_dispositivo_perdido_bloqueia(self):
        saida = TEXTO.replace("art. 7º, inciso IX, da LGPD", "a LGPD")
        self.assertEqual(ver(A.auditar(TEXTO, saida), "valores_sensiveis")["status"], "BLOQUEIO")

    def test_numero_de_processo_alterado_bloqueia(self):
        saida = TEXTO.replace("0001234-56.2024", "0001234-56.2025")
        self.assertEqual(ver(A.auditar(TEXTO, saida), "valores_sensiveis")["status"], "BLOQUEIO")

    def test_citacao_alterada_bloqueia(self):
        antes = 'O tribunal afirmou que "o contrato se extinguiu de pleno direito" e negou o pedido.'
        depois = 'O tribunal afirmou que "o contrato se extinguiu" e negou o pedido.'
        self.assertEqual(ver(A.auditar(antes, depois), "valores_sensiveis")["status"], "BLOQUEIO")

    def test_troca_de_aspas_passa(self):
        antes = "O tribunal afirmou que “o contrato se extinguiu de pleno direito” e negou o pedido."
        depois = 'O tribunal afirmou que "o contrato se extinguiu de pleno direito" e negou o pedido.'
        self.assertEqual(ver(A.auditar(antes, depois), "valores_sensiveis")["status"], "OK")

    def test_campo_preenchido_com_valor_inventado_bloqueia(self):
        antes = "O sinal é de [valor], pago até o fim do mês."
        depois = "O sinal é de R$ 2.000,00, pago até o fim do mês."
        self.assertEqual(ver(A.auditar(antes, depois), "valores_sensiveis")["status"], "BLOQUEIO")


class PerfilDeontico(unittest.TestCase):
    def test_pode_para_deve_bloqueia(self):
        saida = TEXTO.replace("pode rescindir", "deve rescindir")
        self.assertEqual(ver(A.auditar(TEXTO, saida), "perfil_deontico")["status"], "BLOQUEIO")

    def test_proibicao_para_permissao_bloqueia(self):
        antes = "A CONTRATADA não pode subcontratar os Serviços sem anuência."
        depois = "A CONTRATADA pode subcontratar os Serviços sem anuência."
        self.assertEqual(ver(A.auditar(antes, depois), "perfil_deontico")["status"], "BLOQUEIO")

    def test_nao_precisa_conta_como_permissao(self):
        p = A.perfil_deontico("O cliente não precisa assinar o aditivo.")
        self.assertEqual(p["permissao"], 1)
        self.assertEqual(p["obrigacao"], 0)

    def test_moldura_de_discurso_nao_e_norma(self):
        p = A.perfil_deontico("Vale ressaltar que o prazo venceu. Cabe destacar um ponto. Deve-se notar o atraso.")
        self.assertEqual(sum(p.values()), 0)

    def test_remover_moldura_passa(self):
        antes = "É importante destacar que o cliente deve protocolar o pedido no prazo."
        depois = "O cliente deve protocolar o pedido no prazo."
        self.assertEqual(ver(A.auditar(antes, depois), "perfil_deontico")["status"], "OK")

    def test_obrigacao_equivalente_passa(self):
        antes = "O LOCATÁRIO deve devolver as chaves na data da entrega."
        depois = "O LOCATÁRIO é obrigado a devolver as chaves na data da entrega."
        self.assertEqual(ver(A.auditar(antes, depois), "perfil_deontico")["status"], "OK")

    def test_remover_envelope_de_chat_passa(self):
        antes = ("Claro! Aqui está a minuta. O LOCATÁRIO não pode sublocar o imóvel. "
                 "Você pode ajustar o tom ao destinatário. Posso também preparar uma versão curta.")
        depois = "O LOCATÁRIO não pode sublocar o imóvel."
        self.assertEqual(ver(A.auditar(antes, depois), "perfil_deontico")["status"], "OK")

    def test_envelope_nao_mascara_mudanca_da_norma(self):
        antes = "O LOCATÁRIO pode sublocar o imóvel. Você pode ajustar o tom ao destinatário."
        depois = "O LOCATÁRIO deve sublocar o imóvel."
        self.assertEqual(ver(A.auditar(antes, depois), "perfil_deontico")["status"], "BLOQUEIO")


class Certeza(unittest.TestCase):
    def test_incerteza_removida_bloqueia(self):
        r = A.auditar("O tribunal provavelmente decidirá em março.", "O tribunal decidirá em março.")
        self.assertEqual(ver(r, "certeza")["status"], "BLOQUEIO")

    def test_desbastar_hedging_empilhado_passa(self):
        antes = "Poderia-se eventualmente argumentar que a política talvez tenha algum impacto."
        depois = "A política pode afetar o resultado."
        self.assertEqual(ver(A.auditar(antes, depois), "certeza")["status"], "OK")

    def test_incerteza_acrescentada_e_alerta(self):
        r = A.auditar("O tribunal decidirá em março.", "O tribunal provavelmente decidirá em março.")
        self.assertEqual(ver(r, "certeza")["status"], "ALERTA")


class VestigiosDeFerramenta(unittest.TestCase):
    def test_campo_nao_preenchido_bloqueia_prontidao(self):
        antes = "O sinal é de [valor], pago até o fim do mês."
        r = A.auditar(antes, antes)
        self.assertEqual(ver(r, "vestigios_de_ferramenta")["status"], "BLOQUEIO")
        self.assertEqual(ver(r, "valores_sensiveis")["status"], "OK")

    def test_marcador_a_completar_bloqueia_prontidao_mas_nao_e_valor_inventado(self):
        antes = "A adoção cresceu em todo o setor."
        depois = "A adoção cresceu [a completar: fonte para a afirmação de que a adoção cresceu em todo o setor]."
        r = A.auditar(antes, depois)
        self.assertEqual(ver(r, "vestigios_de_ferramenta")["status"], "BLOQUEIO")
        self.assertEqual(ver(r, "valores_sensiveis")["status"], "OK")

    def test_fecho_de_chatbot_bloqueia(self):
        r = A.auditar(TEXTO, TEXTO + " Espero que ajude!")
        self.assertEqual(ver(r, "vestigios_de_ferramenta")["status"], "BLOQUEIO")

    def test_abertura_aqui_esta_bloqueia(self):
        r = A.auditar(TEXTO, "Aqui está a versão revisada: " + TEXTO)
        self.assertEqual(ver(r, "vestigios_de_ferramenta")["status"], "BLOQUEIO")

    def test_oferta_do_assistente_bloqueia(self):
        r = A.auditar(TEXTO, TEXTO + " Você pode ajustar o tom ao destinatário.")
        self.assertEqual(ver(r, "vestigios_de_ferramenta")["status"], "BLOQUEIO")

    def test_fecho_de_email_humano_nao_e_vestigio(self):
        t = "Segue em anexo a minuta da ata. Fico à disposição para qualquer dúvida."
        self.assertEqual(ver(A.auditar(t, t), "vestigios_de_ferramenta")["status"], "OK")


class TermosProtegidos(unittest.TestCase):
    def test_arras_para_adiantamento_bloqueia(self):
        antes = "O comprador pagou arras no valor previsto no compromisso de compra e venda."
        depois = "O comprador pagou um adiantamento no valor previsto no compromisso de compra e venda."
        self.assertEqual(ver(A.auditar(antes, depois), "termos_protegidos")["status"], "BLOQUEIO")

    def test_termo_definido_substituido_bloqueia(self):
        antes = ('Alfa Ltda. (doravante "Contratante") encomenda o serviço. '
                 "A Contratante aceita as Entregas em 7 dias.")
        depois = "Alfa Ltda. encomenda o serviço. A cliente aceita as Entregas em 7 dias."
        self.assertEqual(ver(A.auditar(antes, depois), "termos_protegidos")["status"], "BLOQUEIO")

    def test_termo_em_caixa_alta_substituido_bloqueia(self):
        antes = "A CONTRATANTE pagará a fatura. A CONTRATANTE notificará eventual atraso."
        depois = "A empresa pagará a fatura e notificará eventual atraso."
        self.assertEqual(ver(A.auditar(antes, depois), "termos_protegidos")["status"], "BLOQUEIO")

    def test_menos_usos_de_termo_definido_e_alerta(self):
        antes = ('Alfa Ltda. (doravante "Contratante") encomenda o serviço. '
                 "A Contratante aceita as Entregas. A Contratante paga em 7 dias.")
        depois = ('Alfa Ltda. (doravante "Contratante") encomenda o serviço. '
                  "A Contratante aceita as Entregas e paga em 7 dias.")
        r = A.auditar(antes, depois)
        self.assertEqual(ver(r, "termos_protegidos")["status"], "ALERTA")
        self.assertEqual(r["status"], "ALERTA")

    def test_termo_por_parametro_protegido_literalmente(self):
        antes = "Usamos o Rito Expresso para casos urgentes."
        depois = "Usamos um rito rápido para casos urgentes."
        r = A.auditar(antes, depois, protegidos=["Rito Expresso"])
        self.assertEqual(ver(r, "termos_protegidos")["status"], "BLOQUEIO")

    def test_remover_envelope_nao_muda_contagem_de_termos(self):
        antes = "Aqui está a minuta da apelação. A apelação abrange toda a sentença. Posso preparar outra apelação."
        depois = "A apelação abrange toda a sentença."
        self.assertEqual(ver(A.auditar(antes, depois), "termos_protegidos")["status"], "OK")


class LimiteDeCorte(unittest.TestCase):
    ANTES = " ".join(f"palavra{i}" for i in range(100))

    def test_corte_acima_do_limite_bloqueia(self):
        saida = " ".join(f"palavra{i}" for i in range(50))
        self.assertEqual(ver(A.auditar(self.ANTES, saida), "limite_de_corte")["status"], "BLOQUEIO")

    def test_corte_dentro_do_limite_passa(self):
        saida = " ".join(f"palavra{i}" for i in range(80))
        self.assertEqual(ver(A.auditar(self.ANTES, saida), "limite_de_corte")["status"], "OK")

    def test_texto_curto_acima_do_limite_e_alerta(self):
        antes = "Vale ressaltar que, no cenário atual, o escritório deveria adotar uma solução abrangente e inovadora."
        depois = "O escritório deveria adotar essa solução."
        self.assertEqual(ver(A.auditar(antes, depois), "limite_de_corte")["status"], "ALERTA")

    def test_limite_e_parametro(self):
        saida = " ".join(f"palavra{i}" for i in range(50))
        r = A.auditar(self.ANTES, saida, corte_maximo=0.6)
        self.assertEqual(ver(r, "limite_de_corte")["status"], "OK")


class AchadosNaMedicao(unittest.TestCase):
    """Falsos alarmes achados no conjunto cego (2026-10-13), refeitos aqui como casos sintéticos."""

    def test_abreviacao_dentro_de_palavra_nao_e_dispositivo(self):
        antes = "Entregamos o material. O prazo vence em 10 dias."
        depois = "Entregamos o material; o prazo vence em 10 dias."
        self.assertEqual(ver(A.auditar(antes, depois), "valores_sensiveis")["status"], "OK")

    def test_nota_numerada_nao_e_campo_a_preencher(self):
        t = "Conforme a nota [1], o prazo foi suspenso."
        self.assertEqual(ver(A.auditar(t, t), "vestigios_de_ferramenta")["status"], "OK")

    def test_tirar_envelope_de_chat_nao_conta_no_limite_de_corte(self):
        corpo = ("A CONTRATADA deve entregar os produtos no depósito da CONTRATANTE em até 14 dias do pedido. "
                 "O atraso sujeita a CONTRATADA à multa de 0,5% do preço por semana. "
                 "A CONTRATANTE pode recusar produtos fora da especificação em até 7 dias da entrega.")
        abertura = "Claro! Aqui está uma versão clara e profissional da cláusula que você pediu para ajustar no contrato."
        fecho = ("Espero que ajude na negociação! Se precisar de ajustes, é só avisar. "
                 "Posso também preparar uma versão mais curta para o resumo.")
        r = A.auditar(f"{abertura} {corpo} {fecho}", corpo)
        self.assertEqual(ver(r, "limite_de_corte")["status"], "OK")


class Cli(unittest.TestCase):
    def rodar(self, antes, depois, *args):
        with tempfile.TemporaryDirectory() as d:
            a, b = Path(d, "antes.txt"), Path(d, "depois.txt")
            a.write_text(antes, encoding="utf-8")
            b.write_text(depois, encoding="utf-8")
            return subprocess.run([sys.executable, str(SCRIPT), str(a), str(b), *args],
                                  capture_output=True, text=True, encoding="utf-8")

    def test_codigo_0_quando_ok(self):
        r = self.rodar(TEXTO, TEXTO)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("AUDITORIA PÓS-EDIÇÃO: OK", r.stdout)  # código 0 sozinho não prova nada

    def test_codigo_20_quando_bloqueia(self):
        r = self.rodar(TEXTO, TEXTO.replace("R$ 12.500,00", "R$ 12.000,00"))
        self.assertEqual(r.returncode, 20, r.stdout + r.stderr)
        self.assertIn("BLOQUEIO", r.stdout)

    def test_codigo_2_em_chamada_errada(self):
        self.assertEqual(subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True).returncode, 2)


if __name__ == "__main__":
    unittest.main()
