# Media Metadata Manager

Um script Python para gerenciar metadados de arquivos de mídia, integrando com a API do TMDB e gerando um catálogo HTML interativo.

## Funcionalidades

- 🎬 **Busca automática de metadados**: Obtém informações de filmes/séries do TMDB
- 📁 **Processamento de diretórios**: Escaneia pastas recursivamente em busca de arquivos de mídia
- 🖼️ **Download de pôsteres**: Baixa automaticamente as capas dos conteúdos
- 📝 **Incorporação de metadados**: Usa FFmpeg para adicionar metadados aos arquivos
- 🌐 **Gerador de HTML**: Cria um catálogo visual com abas para filmes e séries
- 📊 **Logs detalhados**: Registra todas as operações em arquivo de log

## Pré-requisitos

- Python 3.8+
- FFmpeg instalado no sistema
- [Chave de API do TMDB](https://www.themoviedb.org/settings/api)

## Instalação

1. Clone o repositório:
```bash
git clone https://github.com/seu-usuario/media-metadata-manager.git
cd media-metadata-manager

    Instale as dependências:



pip install -r requirements.txt

Uso

python media_metadata.py -d "caminho/para/seus/arquivos" -k SUA_CHAVE_API_TMDB

Parâmetros opcionais:

    -f/--ffmpeg: Caminho personalizado para o executável do FFmpeg

    -v: Modo verbose (logging detalhado)

Configuração

    Obtenha uma chave API do TMDB:

        Registre-se em https://www.themoviedb.org

        Acesse as configurações de API e crie uma nova chave

    Formatos suportados:

        Vídeo: MP4, MKV, M4V

        Padrão de nomes:

            Filmes: Nome do Filme (2020).ext ou Nome.do.Filme.2020.ext

            Séries: Nome da Série S01E01.ext

Exemplo de Saída

Exemplo do HTML gerado
Estrutura de Arquivos

Os metadados são armazenados em:
Copy

diretório_raiz/
├── .metadata/
│   ├── posters/
│   └── metadata.json
└── index.html

Notas

    O script preserva os arquivos originais durante o processamento

    Metadados existentes são reutilizados em execuções subsequentes

    Para forçar atualização, delete o arquivo metadata.json

    O HTML gerado inclui links diretos para os arquivos locais

Licença

Distribuído sob licença MIT. Consulte o arquivo LICENSE para mais detalhes.

Aviso: Este projeto não tem afiliação com o TMDB. Os dados são fornecidos conforme os Termos de Uso do TMDB.
