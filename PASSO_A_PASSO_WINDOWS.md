# PynelSAMU - Passo a passo para Windows (para iniciantes)

Este guia explica como rodar o PynelSAMU no Windows, mesmo se você nunca usou Python.

---

## O que você precisa ter instalado

### 1. Python
- Acesse: **https://www.python.org/downloads/**
- Clique em **"Download Python 3.x.x"** (a versão mais recente)
- Abra o arquivo baixado
- **IMPORTANTE:** Marque a caixa **"Add Python to PATH"** (na primeira tela)
- Clique em **"Install Now"**
- Quando terminar, clique em **"Close"**

### 2. Google Chrome
- Acesse: **https://www.google.com/chrome/**
- Baixe e instale o Chrome normalmente
- O programa usa o Chrome em segundo plano; você não precisa abri-lo

---

## Primeira vez: configurar o projeto

### Passo 1: Copiar a pasta do projeto
- Copie a pasta inteira do PynelSAMU para o seu computador
- Sugestão: coloque em `C:\PynelSAMU` ou em `Documentos`
- Evite caminhos com muitos espaços ou caracteres especiais

### Passo 2: Configurar suas credenciais
1. Abra a pasta do projeto no **Explorador de Arquivos**
2. Procure o arquivo **`env.example`**
3. Copie esse arquivo e renomeie a cópia para **`.env`**
4. Clique com o botão direito em **`.env`** → **Abrir com** → **Bloco de Notas**
5. Encontre as linhas:
   ```
   SAMU_USERNAME=seu_usuario_aqui
   SAMU_PASSWORD=sua_senha_aqui
   ```
6. Substitua por seu usuário e senha do sistema SAMU
7. Salve o arquivo (Ctrl+S) e feche

### Passo 3: Executar o script de inicialização
1. Na pasta do projeto, localize o arquivo **`INICIAR_WINDOWS.ps1`**
2. Clique com o **botão direito** nele
3. Selecione **"Executar com PowerShell"**

**Se aparecer erro de "execução de scripts desabilitada":**
1. Abra o **PowerShell** (Windows + R, digite `powershell`, Enter)
2. Digite: `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`
3. Pressione Enter e digite **S** para confirmar
4. Tente novamente o Passo 3

4. Aguarde: na primeira vez o script vai instalar as dependências (pode levar alguns minutos)
5. Quando aparecer **"Iniciando PynelSAMU em http://localhost:5001"**, está pronto

### Passo 4: Abrir no navegador
1. Abra o **Chrome** (ou outro navegador)
2. Na barra de endereço, digite: **http://localhost:5001**
3. Pressione Enter

---

## Uso diário (já configurado)

Toda vez que quiser usar o PynelSAMU:

1. Vá até a pasta do projeto
2. Clique com o botão direito em **`INICIAR_WINDOWS.ps1`**
3. Selecione **"Executar com PowerShell"**
4. Abra o navegador em **http://localhost:5001**

**Para encerrar:** Feche a janela do PowerShell ou pressione Ctrl+C.

---

## Reiniciar o programa

Se precisar reiniciar (por exemplo, após alterar configurações):

1. Feche a janela do PowerShell que está rodando o programa
2. Clique com o botão direito em **`restart.ps1`**
3. Selecione **"Executar com PowerShell"**

---

## Resumo rápido

| O que fazer | Como fazer |
|-------------|------------|
| **Primeira vez** | Configurar .env → Executar INICIAR_WINDOWS.ps1 |
| **Uso normal** | Executar INICIAR_WINDOWS.ps1 → Abrir http://localhost:5001 |
| **Reiniciar** | Executar restart.ps1 |

---

## Problemas comuns

| Problema | Solução |
|---------|---------|
| "python não é reconhecido" | Reinstale o Python e marque **"Add Python to PATH"** |
| Erro ao executar o script | Execute `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser` no PowerShell |
| Página não abre | Verifique se o programa está rodando (janela do PowerShell aberta) e se digitou http://localhost:5001 |
| Erro no download | Verifique usuário e senha no arquivo .env |

---

## Suporte

Em caso de dúvidas, consulte o README.md ou entre em contato com o suporte técnico.
