# Análise das Colunas do Arquivo convertido_tabela.xlsx

## Resumo Geral
- **Total de linhas**: 2.986 ocorrências
- **Total de colunas**: 61 colunas
- **Período**: Dados de 25/01/2026 a 26/01/2026

---

## Categorias de Colunas

### 1. Identificação da Ocorrência (5 colunas)

| Coluna | Tipo | Nulos | Únicos | Observações |
|--------|------|-------|--------|-------------|
| **Ocorrência** | object | 2 (0.1%) | 2.922 | Número único da ocorrência |
| **Código da ocorrência** | str | 7 (0.2%) | 8 | Classificação: Amarelo, Verde, Vermelho, Orientação Médica, etc. |
| **Status da ocorrência** | str | 3 (0.1%) | 5 | Estados: Encerrada, Cancelada, Em Atendimento, Aguardando Despacho/Regulação |
| **Situação atendimento** | str | 22 (0.7%) | 25 | Ex: Queda de ligação, Sem Resposta |
| **Data ocorrência** | datetime | 3 (0.1%) | 2.882 | Data e hora da ocorrência |

### 2. Classificação e Tipo de Atendimento (4 colunas)

| Coluna | Tipo | Nulos | Únicos | Observações |
|--------|------|-------|--------|-------------|
| **Atendimento** | str | 3 (0.1%) | 3 | Com atendimento, Sem atendimento, --- |
| **Transporte** | str | 3 (0.1%) | 3 | Pré-hospitalar, Inter-hospitalar, --- |
| **Tipo** | str | 1.674 (56.1%) | 4 | Clinico, Causas Externas, Gineco/Obstetrico, Psiquiatrico |
| **Motivo** | str | 1.677 (56.2%) | 95 | Códigos PCG (ex: PCG9 OUTRAS QUEIXAS CLÍNICAS) |

### 3. Localização (9 colunas)

| Coluna | Tipo | Nulos | Únicos | Observações |
|--------|------|-------|--------|-------------|
| **Cidade** | str | 1.000 (33.5%) | 75 | Cidades do Espírito Santo |
| **Bairro** | str | 3 (0.1%) | 742 | Muitos valores vazios |
| **Endereço** | str | 3 (0.1%) | 1.068 | Muitos valores vazios |
| **Número** | str | 8 (0.3%) | 467 | Muitos valores vazios |
| **Referência** | str | 3 (0.1%) | 1.538 | Muitos valores vazios |
| **Lat. Local Atendimento** | float64 | 2.449 (82.0%) | 537 | Coordenadas geográficas |
| **Long. Local Atendimento** | float64 | 2.449 (82.0%) | 537 | Coordenadas geográficas |
| **Micro Região** | str | 1.000 (33.5%) | 7 | CIM NORTE, METROPOLITANO 1-3, NOROESTE, SUL |
| **Hospital origem** | str | 3 (0.1%) | 66 | Para transportes inter-hospitalares |
| **Hospital destino** | str | 3 (0.1%) | 92 | Hospital de destino |
| **Lat. Hospital destino** | float64 | 2.571 (86.1%) | 409 | Coordenadas do hospital |
| **Long. Hospital destino** | float64 | 2.571 (86.1%) | 408 | Coordenadas do hospital |

### 4. Dados do Paciente (6 colunas)

| Coluna | Tipo | Nulos | Únicos | Observações |
|--------|------|-------|--------|-------------|
| **Paciente** | str | 3 (0.1%) | 1.237 | Nome do paciente (muitos vazios) |
| **Sexo** | str | 3 (0.1%) | 2 | M (Masculino), F (Feminino) |
| **Idade** | str | 3 (0.1%) | 103 | Idade ou "Não Informada" |
| **Faixa** | str | 3 (0.1%) | 7 | 0-1, 2-9, 10-19, 20-40, 41-60, >60, --- |
| **Risco Inicial** | str | 3 (0.1%) | 6 | Emergência, Muito Urgente, Urgente, Pouco Urgente, Não Urgente, --- |
| **Óbito** | str | 2.475 (82.9%) | 5 | Status do óbito (se houver) |

### 5. Sinais Vitais e Avaliação (6 colunas)

| Coluna | Tipo | Nulos | Únicos | Observações |
|--------|------|-------|--------|-------------|
| **Frq. Respiratória** | float64 | 3 (0.1%) | 28 | 0 a 51 (muitos zeros) |
| **Frq. Cardíaca** | float64 | 3 (0.1%) | 97 | 0 a 776 (muitos zeros) |
| **Pressão Arterial** | str | 3 (0.1%) | 117 | Formato "XXX/YYY" (muitos "0/0") |
| **Escala Glasgow** | float64 | 3 (0.1%) | 14 | 0 a 15 (muitos zeros) |
| **Glicemia** | object | 3 (0.1%) | 166 | Valores de glicemia (muitos zeros) |

### 6. Equipe e Recursos (7 colunas)

| Coluna | Tipo | Nulos | Únicos | Observações |
|--------|------|-------|--------|-------------|
| **Unidade** | str | 2.402 (80.4%) | 106 | USA - AEROMEDICO, USA 10 - VITORIA, etc. |
| **Veículo** | str | 2.402 (80.4%) | 108 | Identificação do veículo |
| **Tec. Enfermagem** | str | 2.499 (83.7%) | 190 | Nome(s) do(s) técnico(s) |
| **Condutor** | str | 2.406 (80.6%) | 234 | Nome do condutor |
| **Enfermeiro** | str | 2.890 (96.8%) | 54 | Nome do enfermeiro (quando presente) |
| **Médico** | str | 2.892 (96.9%) | 46 | Nome do médico (quando presente) |
| **Apoio Polícia Militar** | str | 3 (0.1%) | 2 | Compareceu / Não Compareceu |
| **Apoio Bombeiros** | str | 3 (0.1%) | 2 | Compareceu / Não Compareceu |
| **Apoio USA** | str | 3 (0.1%) | 2 | Compareceu / Não Compareceu |

### 7. Fluxo de Atendimento - Timestamps (11 colunas)

| Coluna | Tipo | Nulos | Observações |
|--------|------|-------|-------------|
| **Tarm** | str | 3 (0.1%) | Nome do TARM (Teleatendimento) |
| **Data Tarm** | datetime | 3 (0.1%) | Data/hora do TARM |
| **Regulador** | str | 1.623 (54.4%) | Nome do regulador médico |
| **Data regulador** | datetime | 1.623 (54.4%) | Data/hora da regulação |
| **Controlador** | str | 2.343 (78.5%) | Nome do controlador |
| **Data controlador** | datetime | 2.343 (78.5%) | Data/hora do controle |
| **Início deslocamento** | datetime | 2.445 (81.9%) | Início do deslocamento |
| **Saída para atendimento** | datetime | 2.407 (80.6%) | Saída da base |
| **Chegada no local** | datetime | 2.449 (82.0%) | Chegada no local |
| **Saída para hospital** | datetime | 2.561 (85.8%) | Saída do local para hospital |
| **Chegada no hospital** | datetime | 2.572 (86.1%) | Chegada no hospital |
| **Atendimento encerrado** | datetime | 2.441 (81.7%) | Fim do atendimento |
| **Chegada na base** | datetime | 2.977 (99.7%) | Retorno à base (muito raro) |

### 8. Protocolos e Contato (3 colunas)

| Coluna | Tipo | Nulos | Únicos | Observações |
|--------|------|-------|--------|-------------|
| **Solicitante** | str | 910 (30.5%) | 1.219 | Quem solicitou o atendimento |
| **Telefone** | str | 3 (0.1%) | 2.171 | Telefone do solicitante |
| **Protocolo telefone** | str | 98 (3.3%) | 2.813 | Protocolo único do telefone |

### 9. Protocolos J14/J15 (4 colunas)

| Coluna | Tipo | Nulos | Observações |
|--------|------|-------|-------------|
| **Primeiro J14** | datetime | 2.515 (84.2%) | Primeiro registro J14 |
| **Último J14** | datetime | 2.515 (84.2%) | Último registro J14 |
| **Primeiro J15** | datetime | 2.511 (84.1%) | Primeiro registro J15 |
| **Último J15** | datetime | 2.511 (84.1%) | Último registro J15 |

---

## Observações Importantes

### Colunas com Alta Taxa de Nulos (>80%)
- **Chegada na base**: 99.7% nulos (quase nunca preenchido)
- **Médico**: 96.9% nulos (médico presente em poucos atendimentos)
- **Enfermeiro**: 96.8% nulos
- **Chegada no hospital**: 86.1% nulos
- **Saída para hospital**: 85.8% nulos
- **Tipo/Motivo**: ~56% nulos (não preenchido em muitos casos)

### Colunas com Valores Vazios Significativos
- Muitas colunas de endereço têm valores vazios (string vazia " ")
- Sinais vitais frequentemente zerados (0.0) quando não medidos

### Colunas Numéricas para Análise
- **Lat/Long**: Coordenadas geográficas para mapeamento
- **Frq. Respiratória/Cardíaca**: Sinais vitais (atenção aos zeros)
- **Escala Glasgow**: 0-15 (0 = não medido)
- **Glicemia**: Valores numéricos

### Colunas de Data/Hora para Cálculo de Tempos
- Sequência temporal: Tarm → Regulador → Controlador → Deslocamento → Atendimento → Hospital → Encerrado
- Permitem calcular tempos de resposta, atendimento, transporte, etc.

### Categorias Principais
- **Código da ocorrência**: Classificação de prioridade (Vermelho, Amarelo, Verde)
- **Status**: Estado atual da ocorrência
- **Tipo**: Categoria clínica (Clínico, Causas Externas, etc.)
- **Micro Região**: Região geográfica do atendimento

---

## Sugestões de Indicadores

1. **Tempos de Resposta**:
   - Tempo TARM → Regulador
   - Tempo Regulador → Início Deslocamento
   - Tempo Deslocamento → Chegada no Local
   - Tempo no Local (Chegada → Saída)
   - Tempo Transporte (Saída → Chegada Hospital)

2. **Distribuições**:
   - Por Código da Ocorrência (Vermelho/Amarelo/Verde)
   - Por Tipo (Clínico, Causas Externas, etc.)
   - Por Micro Região
   - Por Status da Ocorrência

3. **Taxa de Preenchimento**:
   - Sinais vitais medidos
   - Dados de localização completos
   - Equipe presente

4. **Geográficos**:
   - Mapa de ocorrências (Lat/Long)
   - Distribuição por cidade/micro região
   - Rotas mais frequentes

5. **Equipe**:
   - Atendimentos por unidade/veículo
   - Atendimentos por profissional
   - Taxa de apoio (PM, Bombeiros, USA)
