"""
UNIVERSIDADE Nove de Julho
CURSO: BACHARELADO EM SISTEMAS DE INFORMAÇÃO
DISCIPLINA: DESENVOLVIMENTO DE SISTEMAS

PROJETO: SGI - SISTEMA DE GESTÃO INTEGRADA (MÓDULO VENDAS)
OBJETIVO: Implementar um sistema transacional com persistência em banco relacional,
respeitando os princípios ACID e mantendo log de auditoria.
"""

import sqlite3
import datetime
import os

# --- CAMADA DE INFRAESTRUTURA E LOGS (CRUCIAL PARA SI) ---
class Logger:
    @staticmethod
    def registrar(acao, detalhes):
        """Registra operações críticas para auditoria do sistema."""
        data = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[LOG {data}] {acao.upper()}: {detalhes}")
        # Em um sistema real, isso seria salvo em uma tabela 'tb_logs'

# --- CAMADA DE PERSISTÊNCIA (MODEL) ---
class BancoDados:
    def __init__(self):
        self.conn = sqlite3.connect('sgi_database.db')
        self.cursor = self.conn.cursor()
        self._setup()

    def _setup(self):
        # DDL - Definição de Dados
        # Tabela normalizada (3FN)
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS clientes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                razao_social TEXT NOT NULL,
                cnpj_cpf TEXT UNIQUE NOT NULL,
                ativo BOOLEAN DEFAULT 1
            )
        ''')
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS produtos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                preco_venda REAL NOT NULL,
                saldo_estoque INTEGER NOT NULL
            )
        ''')
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS pedidos_venda (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cliente_id INTEGER,
                data_emissao DATETIME,
                valor_total REAL,
                FOREIGN KEY(cliente_id) REFERENCES clientes(id)
            )
        ''')
        self.conn.commit()

# --- CAMADA DE REGRA DE NEGÓCIO (CONTROLLER) ---
class GestorVendas:
    def __init__(self):
        self.db = BancoDados()

    def cadastrar_cliente(self, nome, doc):
        try:
            self.db.cursor.execute("INSERT INTO clientes (razao_social, cnpj_cpf) VALUES (?, ?)", (nome, doc))
            self.db.conn.commit()
            Logger.registrar("CADASTRO", f"Cliente {nome} inserido.")
            return True
        except sqlite3.IntegrityError:
            Logger.registrar("ERRO", f"Tentativa de cadastro duplicado para {doc}.")
            return False

    def processar_venda(self, id_cli, id_prod, qtd):
        # 1. Busca dados (Leitura)
        produto = self.db.cursor.execute("SELECT preco_venda, saldo_estoque FROM produtos WHERE id=?", (id_prod,)).fetchone()
        
        if not produto:
            return "Produto não encontrado."
        
        preco, estoque = produto

        # 2. Validação de Regra de Negócio (Estoque não pode ser negativo)
        if estoque < qtd:
            Logger.registrar("FALHA_VENDA", f"Estoque insuficiente Prod ID {id_prod}.")
            return "Saldo de estoque insuficiente."

        # 3. Transação (Atomicidade)
        total = preco * qtd
        data = datetime.datetime.now()
        
        try:
            self.db.cursor.execute("UPDATE produtos SET saldo_estoque = ? WHERE id = ?", (estoque - qtd, id_prod))
            self.db.cursor.execute("INSERT INTO pedidos_venda (cliente_id, data_emissao, valor_total) VALUES (?, ?, ?)", 
                                   (id_cli, data, total))
            self.db.conn.commit()
            Logger.registrar("VENDA", f"Venda ID {id_cli} | Valor R${total:.2f}")
            return "Venda processada com sucesso."
        except Exception as e:
            self.db.conn.rollback() # Desfaz tudo se der erro
            return f"Erro no processamento: {e}"

# --- CAMADA DE APRESENTAÇÃO (VIEW) ---
def iniciar_sistema():
    sistema = GestorVendas()
    # Seed (Dados iniciais para teste)
    sistema.db.cursor.execute("INSERT OR IGNORE INTO produtos (id, nome, preco_venda, saldo_estoque) VALUES (1, 'Licença ERP Standard', 1500.00, 10)")
    sistema.db.conn.commit()

    while True:
        print("\n--- SGI V 1.0 (AMBIENTE DE HOMOLOGAÇÃO) ---")
        print("1. Cadastrar Cliente")
        print("2. Nova Venda")
        print("3. Sair")
        op = input("Opção: ")

        if op == '1':
            nome = input("Razão Social: ")
            doc = input("CNPJ/CPF: ")
            if sistema.cadastrar_cliente(nome, doc):
                print(">> Sucesso.")
            else:
                print(">> Erro: Documento já existe.")
        elif op == '2':
            try:
                cli = int(input("ID Cliente: "))
                prod = int(input("ID Produto (Use 1 para teste): "))
                qtd = int(input("Quantidade: "))
                msg = sistema.processar_venda(cli, prod, qtd)
                print(f">> {msg}")
            except ValueError:
                print(">> Erro de entrada de dados.")
        elif op == '3':
            break

if __name__ == "__main__":
    iniciar_sistema()