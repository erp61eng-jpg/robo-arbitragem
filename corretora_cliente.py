C:\Projetos\robo_arbitragem>cd /d C:\Projetos\robo_arbitragem&&python -c "import corretora_cliente as cc;cli=cc.ClienteBinanceOKX();print('pwd_len:',len(getattr(cli.okx,'password',None) or ''));lines=open('corretora_cliente.py',encoding='utf-8').read().splitlines();print('\n'.join(f'{i+1}: {lines[i]}' for i in range(69,min(115,len(lines)))))"
pwd_len: 0
70:         okx_api_key: str | None = None,
71:         okx_secret: str | None = None,
72:         okx_password: str | None = None,
73:     ) -> None:
74:         carregar_env_local()
75:
76:         b_key = binance_api_key or os.getenv("BINANCE_API_KEY") or os.getenv("API_KEY_BINANCE") or ""
77:         b_sec = binance_secret or os.getenv("BINANCE_SECRET") or os.getenv("BINANCE_API_SECRET") or os.getenv("SECRET_BINANCE") or ""
78:
79:         o_key = okx_api_key or os.getenv("OKX_API_KEY") or os.getenv("API_KEY_OKX") or ""
80:         o_sec = okx_secret or os.getenv("OKX_SECRET") or os.getenv("OKX_API_SECRET") or os.getenv("SECRET_OKX") or ""
81:         o_pwd = (
82:             okx_password
83:             or os.getenv("OKX_PASSWORD")
84:             or os.getenv("OKX_PASSPHRASE")
85:             or os.getenv("PASSPHRASE_OKX")
86:             or ""
87:         )
88:
89:         self.binance = ccxt.binance(
90:             {
91:                 "apiKey": b_key,
92:                 "secret": b_sec,
93:                 "enableRateLimit": True,
94:                 "options": {"defaultType": "spot"},
95:             }
96:         )
97:         self.okx = ccxt.okx(
98:             {
99:                 "apiKey": o_key,
100:                 "secret": o_sec,
101:                 "password": o_pwd,
102:                 "enableRateLimit": True,
103:                 "options": {"defaultType": "spot"},
104:             }
105:         )
106:
107:     def _garantir_mercados(self, ativo: str) -> None:
108:         if self.binance is None or self.okx is None:
109:             raise RuntimeError("Clientes ccxt da Binance e OKX nao estao inicializados.")
110:         self.binance.load_markets()
111:         self.okx.load_markets()
112:         if ativo not in self.binance.markets or ativo not in self.okx.markets:
113:             raise ValueError(f"Ativo {ativo} nao disponivel em ambos os mercados spot.")
114:
115:     def _taxas_somadas_pct(self, ativo: str) -> float:

C:\Projetos\robo_arbitragem>
