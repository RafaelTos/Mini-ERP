"""
UNIVERSIDADE Nove de Julho
CURSO: BACHARELADO EM SISTEMAS DE INFORMAÇÃO
DISCIPLINA: DESENVOLVIMENTO DE SISTEMAS

PROJETO: SGI - SISTEMA DE GESTÃO INTEGRADA (MÓDULO VENDAS) - VERSÃO 2.0
OBJETIVO: Implementar um sistema transacional com persistência em banco relacional,
respeitando os princípios ACID e mantendo log de auditoria real.
"""

import sqlite3
import datetime

# --- CAMADA DE INFRAESTRUTURA E BANCO DE DADOS ---
class BancoDados:
    def __init__(self):
        self.conn = sqlite3.connect('sgi_v2_database.db')
        # Habilita o uso de Foreign Keys no SQLite (desligado por padrão)
        self.conn.execute("PRAGMA foreign_keys = ON;")
        self.cursor = self.conn.cursor()
        self._setup()

    def _setup(self):
        """DDL - Definição do Esquema Relacional Normalizado"""
        
        self.cursor.executescript('''
            CREATE TABLE IF NOT EXISTS clientes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                razao_social TEXT NOT NULL,
                cnpj_cpf TEXT UNIQUE NOT NULL,
                ativo BOOLEAN DEFAULT 1
            );
            
            CREATE TABLE IF NOT EXISTS produtos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                preco_venda REAL NOT NULL,
                saldo_estoque INTEGER NOT NULL CHECK(saldo_estoque >= 0)
            );
            
            CREATE TABLE IF NOT EXISTS pedidos_venda (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cliente_id INTEGER NOT NULL,
                data_emissao DATETIME NOT NULL,
                valor_total REAL NOT NULL,
                FOREIGN KEY(cliente_id) REFERENCES clientes(id)
            );
            
            CREATE TABLE IF NOT EXISTS itens_pedido (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pedido_id INTEGER NOT NULL,
                produto_id INTEGER NOT NULL,
                quantidade INTEGER NOT NULL CHECK(quantidade > 0),
                preco_unitario REAL NOT NULL,
                FOREIGN KEY(pedido_id) REFERENCES pedidos_venda(id),
                FOREIGN KEY(produto_id) REFERENCES produtos(id)
            );
            
            CREATE TABLE IF NOT EXISTS logs_auditoria (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data_hora DATETIME NOT NULL,
                acao TEXT NOT NULL,
                detalhes TEXT NOT NULL
            );
        ''')
        self.conn.commit()

# --- CAMADA DE AUDITORIA ---
class Logger:
    @staticmethod
    def registrar(db: BancoDados, acao: str, detalhes: str):
        """Salva operações críticas no banco de dados e exibe no console."""
        data_atual = datetime.datetime.now()
        db.cursor.execute(
            "INSERT INTO logs_auditoria (data_hora, acao, detalhes) VALUES (?, ?, ?)",
            (data_atual, acao.upper(), detalhes)
        )
        db.conn.commit()
        print(f"[LOG {data_atual.strftime('%H:%M:%S')}] {acao.upper()}: {detalhes}")

# --- CAMADA DE REGRA DE NEGÓCIO (CONTROLLER) ---
class GestorVendas:
    def __init__(self):
        self.db = BancoDados()

    def cadastrar_cliente(self, nome: str, doc: str):
        try:
            self.db.cursor.execute("INSERT INTO clientes (razao_social, cnpj_cpf) VALUES (?, ?)", (nome, doc))
            self.db.conn.commit()
            Logger.registrar(self.db, "CADASTRO_CLIENTE", f"Cliente '{nome}' (Doc: {doc}) inserido com sucesso.")
            return True, "Cliente cadastrado."
        except sqlite3.IntegrityError:
            Logger.registrar(self.db, "ERRO_CADASTRO", f"Tentativa de duplicidade para o documento {doc}.")
            return False, "Erro: Documento já cadastrado."

    def processar_venda(self, id_cli: int, id_prod: int, qtd: int):
        """
        Garante as propriedades ACID usando o context manager do SQLite (with self.db.conn).
        Se qualquer erro ocorrer no bloco 'with', um ROLLBACK automático é feito.
        """
        try:
            # Início da Transação explícita
            with self.db.conn:
                # 1. Valida Cliente
                cliente = self.db.cursor.execute("SELECT id FROM clientes WHERE id=?", (id_cli,)).fetchone()
                if not cliente:
                    raise ValueError("Cliente não encontrado.")

                # 2. Valida Produto e Estoque
                produto = self.db.cursor.execute("SELECT nome, preco_venda, saldo_estoque FROM produtos WHERE id=?", (id_prod,)).fetchone()
                if not produto:
                    raise ValueError("Produto não encontrado.")
                
                nome_prod, preco, estoque = produto

                if estoque < qtd:
                    raise ValueError(f"Estoque insuficiente. Saldo atual de '{nome_prod}': {estoque}.")

                # 3. Executa as operações de escrita (DML)
                valor_total = preco * qtd
                data_atual = datetime.datetime.now()

                # A) Baixa no estoque
                self.db.cursor.execute("UPDATE produtos SET saldo_estoque = ? WHERE id = ?", (estoque - qtd, id_prod))

                # B) Cria o cabeçalho do Pedido
                self.db.cursor.execute(
                    "INSERT INTO pedidos_venda (cliente_id, data_emissao, valor_total) VALUES (?, ?, ?)",
                    (id_cli, data_atual, valor_total)
                )
                pedido_id = self.db.cursor.lastrowid # Pega o ID do pedido recém-criado

                # C) Insere o Item do Pedido (Relacional)
                self.db.cursor.execute(
                    "INSERT INTO itens_pedido (pedido_id, produto_id, quantidade, preco_unitario) VALUES (?, ?, ?, ?)",
                    (pedido_id, id_prod, qtd, preco)
                )

            # Se o código chegou aqui sem disparar exceções, o COMMIT foi feito pelo 'with'.
            Logger.registrar(self.db, "VENDA_CONCLUIDA", f"Pedido {pedido_id} | Cliente {id_cli} | Valor R${valor_total:.2f}")
            return True, f"Venda nº {pedido_id} processada com sucesso!"

        except ValueError as ve:
            # Erros de regra de negócio
            Logger.registrar(self.db, "FALHA_VENDA", str(ve))
            return False, str(ve)
        except Exception as e:
            # Erros inesperados (banco, sintaxe, etc)
            Logger.registrar(self.db, "ERRO_SISTEMA", f"Falha crítica na venda: {str(e)}")
            return False, "Erro interno ao processar a venda. Transação cancelada (Rollback)."

# --- CAMADA DE APRESENTAÇÃO (VIEW CLI) ---
def iniciar_sistema():
    sistema = GestorVendas()
    
    # Carga Inicial (Seed) apenas para não precisar cadastrar produto toda vez
    sistema.db.cursor.execute("INSERT OR IGNORE INTO produtos (id, nome, preco_venda, saldo_estoque) VALUES (1, 'Licença ERP Master', 2500.00, 50)")
    sistema.db.cursor.execute("INSERT OR IGNORE INTO produtos (id, nome, preco_venda, saldo_estoque) VALUES (2, 'Suporte Técnico 10h', 800.00, 100)")
    sistema.db.conn.commit()

    while True:
        print("\n" + "="*40)
        print(" SGI V 2.0 - MÓDULO DE VENDAS ".center(40, "="))
        print("="*40)
        print("1. Cadastrar Cliente")
        print("2. Nova Venda")
        print("3. Visualizar Estoque")
        print("4. Sair")
        
        op = input("\nSelecione uma opção: ")

        if op == '1':
            nome = input("Razão Social: ")
            doc = input("CNPJ/CPF: ")
            sucesso, msg = sistema.cadastrar_cliente(nome, doc)
            print(f"> {msg}")
            
        elif op == '2':
            try:
                cli = int(input("ID Cliente: "))
                print("\n[Produtos Disponíveis]")
                for row in sistema.db.cursor.execute("SELECT id, nome, preco_venda, saldo_estoque FROM produtos"):
                    print(f"ID: {row[0]} | {row[1]} | R$ {row[2]:.2f} | Estoque: {row[3]}")
                
                prod = int(input("\nID do Produto desejado: "))
                qtd = int(input("Quantidade: "))
                
                sucesso, msg = sistema.processar_venda(cli, prod, qtd)
                if sucesso:
                    print(f"\n✅ {msg}")
                else:
                    print(f"\n❌ {msg}")
            except ValueError:
                print("\n❌ Erro: Por favor, digite apenas números para IDs e Quantidades.")
                
        elif op == '3':
            print("\n--- Posição de Estoque ---")
            for row in sistema.db.cursor.execute("SELECT id, nome, saldo_estoque FROM produtos"):
                print(f"ID {row[0]}: {row[1]} -> {row[2]} unidades")
                
        elif op == '4':
            print("Encerrando SGI... Até logo!")
            break
        else:
            print("Opção inválida.")

if __name__ == "__main__":
    iniciar_sistema()
