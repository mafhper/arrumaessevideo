import os
import re
import json
import requests
import shutil
import tempfile
import subprocess
from pathlib import Path
import argparse
from typing import Dict, List, Optional, Tuple
import logging
from concurrent.futures import ThreadPoolExecutor

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler("media_metadata.log"), logging.StreamHandler()]
)
logger = logging.getLogger("MediaMetadataManager")

# TMDB API - Você precisará se registrar em https://www.themoviedb.org/ para obter uma chave API
API_KEY = "SUA_CHAVE_API_TMDB_AQUI"
TMDB_API_URL = "https://api.themoviedb.org/3"
POSTER_BASE_URL = "https://image.tmdb.org/t/p/w500"

class MediaMetadataManager:
    def __init__(self, directory: str, api_key: str, ffmpeg_path: str = None):
        self.directory = Path(directory)
        self.api_key = api_key
        self.ffmpeg_path = ffmpeg_path or self._find_ffmpeg()
        self.metadata_dir = self.directory / ".metadata"
        self.posters_dir = self.metadata_dir / "posters"
        self.metadata_file = self.metadata_dir / "metadata.json"
        
        # Verificar se FFmpeg está disponível
        if not self.ffmpeg_path:
            logger.error("FFmpeg não encontrado. Este programa requer FFmpeg para incorporar metadados.")
            raise RuntimeError("FFmpeg não encontrado. Instale FFmpeg e tente novamente.")
        
        logger.info(f"Usando FFmpeg em: {self.ffmpeg_path}")
        
        # Garantir que os diretórios existam
        self.metadata_dir.mkdir(exist_ok=True)
        self.posters_dir.mkdir(exist_ok=True)
        
        # Carregar metadados existentes
        self.metadata = self._load_metadata()
        
        # Extensões de arquivo de vídeo suportadas
        self.video_extensions = {'.mp4', '.mkv', '.m4v'}  # Limitados aos formatos que melhor suportam metadados
    
    def _find_ffmpeg(self) -> Optional[str]:
        """Tenta localizar o binário do FFmpeg no sistema"""
        try:
            # Tenta encontrar usando o comando 'which' no Unix ou 'where' no Windows
            if os.name == 'nt':  # Windows
                result = subprocess.run(['where', 'ffmpeg'], capture_output=True, text=True)
                if result.returncode == 0:
                    return result.stdout.strip().split('\n')[0]
            else:  # Unix/Linux/Mac
                result = subprocess.run(['which', 'ffmpeg'], capture_output=True, text=True)
                if result.returncode == 0:
                    return result.stdout.strip()
            
            # Procura em locais comuns
            common_locations = [
                '/usr/bin/ffmpeg',
                '/usr/local/bin/ffmpeg',
                '/opt/homebrew/bin/ffmpeg',  # macOS com Homebrew
                'C:\\Program Files\\ffmpeg\\bin\\ffmpeg.exe',
                'C:\\ffmpeg\\bin\\ffmpeg.exe'
            ]
            
            for location in common_locations:
                if os.path.isfile(location):
                    return location
            
            return None
        except Exception as e:
            logger.error(f"Erro ao procurar FFmpeg: {str(e)}")
            return None
    
    def _load_metadata(self) -> Dict:
        """Carrega os metadados existentes do arquivo JSON"""
        if self.metadata_file.exists():
            try:
                with open(self.metadata_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except json.JSONDecodeError:
                logger.error(f"Erro ao ler o arquivo de metadados. Criando um novo.")
                return {}
        return {}
    
    def _save_metadata(self) -> None:
        """Salva os metadados no arquivo JSON"""
        with open(self.metadata_file, 'w', encoding='utf-8') as f:
            json.dump(self.metadata, f, ensure_ascii=False, indent=4)
    
    def _parse_filename(self, filename: str) -> Tuple[str, Optional[int], str]:
        """
        Extrai informações do nome do arquivo.
        Retorna (título, ano, tipo) onde tipo é "movie" ou "tv"
        """
        # Padrão para filmes: Nome do Filme (2020).mp4 ou Nome.do.Filme.2020.mp4
        movie_pattern1 = r"(.+)\((\d{4})\).*"
        movie_pattern2 = r"(.+)\.(\d{4})\."
        
        # Padrão para séries: Nome da Série S01E01.mp4 ou Nome.da.Serie.S01E01.mp4
        tv_pattern = r"(.+)[sS](\d+)[eE](\d+)"
        
        # Tenta encontrar um filme com ano entre parênteses
        match = re.match(movie_pattern1, filename)
        if match:
            title = match.group(1).strip().replace(".", " ")
            year = int(match.group(2))
            return title, year, "movie"
        
        # Tenta encontrar um filme com ano no formato Nome.Do.Filme.2020
        match = re.match(movie_pattern2, filename)
        if match:
            title = match.group(1).strip().replace(".", " ")
            year = int(match.group(2))
            return title, year, "movie"
        
        # Tenta encontrar uma série
        match = re.match(tv_pattern, filename)
        if match:
            title = match.group(1).strip().replace(".", " ")
            return title, None, "tv"
        
        # Se não encontrou nenhum padrão, assume que é um filme sem ano
        return filename.split('.')[0].replace(".", " "), None, "movie"
    
    def _search_tmdb(self, title: str, year: Optional[int], media_type: str) -> Optional[Dict]:
        """Busca metadados na API do TMDB"""
        logger.info(f"Buscando metadados para: {title} ({year if year else 'Sem ano'}) - Tipo: {media_type}")
        
        # Preparar URL de busca
        search_url = f"{TMDB_API_URL}/search/{media_type}"
        params = {
            "api_key": self.api_key,
            "query": title,
            "language": "pt-BR"
        }
        
        if year and media_type == "movie":
            params["year"] = year
        
        try:
            response = requests.get(search_url, params=params)
            response.raise_for_status()
            results = response.json().get("results", [])
            
            if not results:
                logger.warning(f"Nenhum resultado encontrado para: {title}")
                return None
            
            # Pegar o primeiro resultado
            result = results[0]
            
            # Buscar detalhes adicionais
            details_url = f"{TMDB_API_URL}/{media_type}/{result['id']}"
            details_params = {
                "api_key": self.api_key,
                "language": "pt-BR",
                "append_to_response": "credits,keywords"
            }
            
            details_response = requests.get(details_url, params=details_params)
            details_response.raise_for_status()
            detailed_info = details_response.json()
            
            # Baixar o pôster se disponível
            poster_path = detailed_info.get("poster_path")
            local_poster_path = None
            
            if poster_path:
                poster_url = f"{POSTER_BASE_URL}{poster_path}"
                local_poster_path = str(self.posters_dir / f"{result['id']}.jpg")
                
                # Baixar o pôster
                poster_response = requests.get(poster_url, stream=True)
                poster_response.raise_for_status()
                
                with open(local_poster_path, 'wb') as out_file:
                    shutil.copyfileobj(poster_response.raw, out_file)
            
            # Extrair informações do elenco
            cast = detailed_info.get("credits", {}).get("cast", [])
            cast_list = []
            for actor in cast[:5]:  # Limitar a 5 atores
                if "name" in actor and "character" in actor:
                    cast_list.append({
                        "name": actor["name"], 
                        "character": actor["character"]
                    })
            
            # Extrair diretores/criadores
            crew = detailed_info.get("credits", {}).get("crew", [])
            directors = []
            for person in crew:
                if person.get("job") == "Director" or person.get("job") == "Creator":
                    directors.append(person["name"])
            
            # Tratar o caso de episode_run_time ser uma lista vazia
            runtime = 0
            if media_type == "movie":
                runtime = detailed_info.get("runtime", 0) or 0
            else:
                episode_run_time = detailed_info.get("episode_run_time", [])
                if isinstance(episode_run_time, list) and episode_run_time:
                    runtime = episode_run_time[0]
            
            # Garantir que o ano seja uma string válida
            year_str = ""
            if year:
                year_str = str(year)
            elif media_type == "movie" and detailed_info.get("release_date"):
                parts = detailed_info.get("release_date", "").split("-")
                if parts and len(parts[0]) == 4:  # Verificar se o formato da data está correto
                    year_str = parts[0]
            elif media_type == "tv" and detailed_info.get("first_air_date"):
                parts = detailed_info.get("first_air_date", "").split("-")
                if parts and len(parts[0]) == 4:
                    year_str = parts[0]
            
            # Criar objeto de metadados
            metadata = {
                "id": detailed_info["id"],
                "title": detailed_info.get("title" if media_type == "movie" else "name", title),
                "original_title": detailed_info.get("original_title" if media_type == "movie" else "original_name", ""),
                "year": year_str,
                "overview": detailed_info.get("overview", ""),
                "poster_path": local_poster_path,
                "genres": [genre["name"] for genre in detailed_info.get("genres", [])],
                "rating": detailed_info.get("vote_average", 0),
                "type": media_type,
                "directors": directors,
                "cast": cast_list,
                "runtime": runtime,
            }
            
            logger.info(f"Metadados encontrados para: {title}")
            return metadata
            
        except requests.RequestException as e:
            logger.error(f"Erro ao buscar metadados para {title}: {str(e)}")
            return None
    
    def _apply_metadata_to_file(self, file_path: Path, metadata: Dict) -> bool:
        """Aplica os metadados ao arquivo de vídeo usando FFmpeg"""
        logger.info(f"Aplicando metadados ao arquivo: {file_path}")
        
        try:
            # Criar um arquivo temporário para a saída
            temp_dir = tempfile.gettempdir()
            temp_output = Path(temp_dir) / f"temp_{file_path.name}"
            
            # Preparar os metadados para FFmpeg
            metadata_args = []
            
            # Metadados básicos - Garantir que todos os valores sejam strings
            metadata_args.extend([
                "-metadata", f"title={metadata.get('title', '')}",
                "-metadata", f"date={metadata.get('year', '')}",
                "-metadata", f"description={metadata.get('overview', '')}",
                "-metadata", f"genre={', '.join(metadata.get('genres', []))}",
                "-metadata", f"rating={str(metadata.get('rating', 0))}",
            ])
            
            # Adicionar diretores e elenco quando disponíveis
            if metadata.get("directors"):
                metadata_args.extend(["-metadata", f"director={', '.join(metadata['directors'])}"])
            
            # Processar elenco com segurança
            actors = []
            for actor in metadata.get("cast", []):
                if isinstance(actor, dict) and "name" in actor:
                    actors.append(actor["name"])
            
            if actors:
                metadata_args.extend(["-metadata", f"artist={', '.join(actors)}"])
            
            # Comando para incorporar metadados e capa
            cmd = [self.ffmpeg_path, "-i", str(file_path)]
            
            # Adicionar pôster se disponível
            poster_path = metadata.get("poster_path")
            if poster_path and os.path.exists(poster_path):
                cmd.extend(["-i", poster_path, "-map", "0", "-map", "1", "-c", "copy", 
                           "-disposition:v:1", "attached_pic"])
            else:
                cmd.extend(["-c", "copy"])
            
            # Adicionar todos os metadados
            cmd.extend(metadata_args)
            
            # Caminho de saída
            cmd.append(str(temp_output))
            
            # Executar o comando
            logger.debug(f"Executando comando FFmpeg: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                logger.error(f"Erro ao aplicar metadados: {result.stderr}")
                return False
            
            # Substituir o arquivo original pelo novo com metadados
            os.replace(temp_output, file_path)
            logger.info(f"Metadados aplicados com sucesso para: {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"Falha ao aplicar metadados: {str(e)}")
            return False
    
    def scan_directory(self) -> None:
        """Escaneia o diretório em busca de arquivos de mídia, atualiza os metadados e os aplica aos arquivos"""
        logger.info(f"Escaneando diretório: {self.directory}")
        
        # Coletar todos os arquivos de vídeo
        media_files = []
        for root, _, files in os.walk(self.directory):
            for file in files:
                file_path = Path(root) / file
                if file_path.suffix.lower() in self.video_extensions:
                    media_files.append(file_path)
        
        logger.info(f"Encontrados {len(media_files)} arquivos de mídia")
        
        # Processar arquivos
        processed_count = 0
        new_files = 0
        
        for file_path in media_files:
            relative_path = str(file_path.relative_to(self.directory))
            
            # Verificar se já temos metadados para este arquivo
            existing_metadata = self.metadata.get(relative_path)
            
            if not existing_metadata:
                new_files += 1
                title, year, media_type = self._parse_filename(file_path.stem)
                
                # Buscar metadados
                metadata = self._search_tmdb(title, year, media_type)
                if metadata:
                    self.metadata[relative_path] = metadata
                    existing_metadata = metadata
            
            # Aplicar metadados ao arquivo se disponíveis
            if existing_metadata:
                success = self._apply_metadata_to_file(file_path, existing_metadata)
                if success:
                    processed_count += 1
        
        logger.info(f"Adicionados metadados para {new_files} novos arquivos")
        logger.info(f"Aplicados metadados a {processed_count} arquivo(s)")
        self._save_metadata()
    
    def generate_html_index(self) -> None:
        """Gera um arquivo HTML para visualizar a coleção de mídia com pôsteres"""
        logger.info("Gerando índice HTML")
        html_path = self.directory / "index.html"
        
        movies = []
        tv_shows = []
        
        for file_path, metadata in self.metadata.items():
            if metadata["type"] == "movie":
                movies.append((file_path, metadata))
            else:
                tv_shows.append((file_path, metadata))
        
        # Ordenar por título
        movies.sort(key=lambda x: x[1]["title"])
        tv_shows.sort(key=lambda x: x[1]["title"])
        
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write("""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Coleção de Mídia</title>
                <style>
                    body { font-family: Arial, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5; }
                    h1, h2 { color: #333; }
                    .media-grid { display: flex; flex-wrap: wrap; gap: 20px; }
                    .media-card { 
                        width: 200px; 
                        background: white; 
                        border-radius: 8px; 
                        overflow: hidden;
                        box-shadow: 0 4px 8px rgba(0,0,0,0.1);
                        transition: transform 0.3s;
                    }
                    .media-card:hover { transform: translateY(-5px); }
                    .poster { width: 100%; height: 300px; object-fit: cover; }
                    .media-info { padding: 10px; }
                    .media-title { font-weight: bold; font-size: 16px; margin-bottom: 5px; }
                    .media-year { color: #666; margin-bottom: 5px; }
                    .media-rating { color: #ff9900; margin-bottom: 5px; }
                    .media-genres { font-size: 12px; color: #333; }
                    .media-play { 
                        display: block; 
                        background: #4CAF50; 
                        color: white; 
                        text-align: center; 
                        padding: 8px; 
                        text-decoration: none; 
                        margin-top: 10px;
                        border-radius: 4px;
                    }
                    .tabs { margin-bottom: 20px; }
                    .tab-button {
                        background: #ddd;
                        border: none;
                        padding: 10px 20px;
                        cursor: pointer;
                        border-radius: 4px 4px 0 0;
                    }
                    .tab-button.active {
                        background: #fff;
                    }
                    .tab-content {
                        display: none;
                        padding: 20px;
                        background: white;
                        border-radius: 0 4px 4px 4px;
                    }
                    .tab-content.active {
                        display: block;
                    }
                </style>
            </head>
            <body>
                <h1>Minha Coleção de Mídia</h1>
                
                <div class="tabs">
                    <button class="tab-button active" onclick="openTab(event, 'movies')">Filmes</button>
                    <button class="tab-button" onclick="openTab(event, 'tvshows')">Séries</button>
                </div>
                
                <div id="movies" class="tab-content active">
                    <h2>Filmes</h2>
                    <div class="media-grid">
            """)
            
            # Adicionar filmes
            for file_path, movie in movies:
                poster = movie.get("poster_path", "")
                poster_html = f'<img class="poster" src="{poster}" alt="{movie["title"]}">' if poster else '<div class="poster" style="background:#ddd;display:flex;align-items:center;justify-content:center;">Sem pôster</div>'
                
                f.write(f"""
                <div class="media-card">
                    {poster_html}
                    <div class="media-info">
                        <div class="media-title">{movie["title"]}</div>
                        <div class="media-year">{movie["year"]}</div>
                        <div class="media-rating">★ {movie["rating"]}/10</div>
                        <div class="media-genres">{', '.join(movie["genres"][:3])}</div>
                        <a href="file://{self.directory / file_path}" class="media-play">Assistir</a>
                    </div>
                </div>
                """)
            
            f.write("""
                    </div>
                </div>
                
                <div id="tvshows" class="tab-content">
                    <h2>Séries</h2>
                    <div class="media-grid">
            """)
            
            # Adicionar séries
            for file_path, show in tv_shows:
                poster = show.get("poster_path", "")
                poster_html = f'<img class="poster" src="{poster}" alt="{show["title"]}">' if poster else '<div class="poster" style="background:#ddd;display:flex;align-items:center;justify-content:center;">Sem pôster</div>'
                
                f.write(f"""
                <div class="media-card">
                    {poster_html}
                    <div class="media-info">
                        <div class="media-title">{show["title"]}</div>
                        <div class="media-year">{show["year"]}</div>
                        <div class="media-rating">★ {show["rating"]}/10</div>
                        <div class="media-genres">{', '.join(show["genres"][:3])}</div>
                        <a href="file://{self.directory / file_path}" class="media-play">Assistir</a>
                    </div>
                </div>
                """)
            
            f.write("""
                    </div>
                </div>
                
                <script>
                    function openTab(evt, tabName) {
                        var i, tabContent, tabButtons;
                        
                        // Esconder todo o conteúdo das abas
                        tabContent = document.getElementsByClassName("tab-content");
                        for (i = 0; i < tabContent.length; i++) {
                            tabContent[i].className = tabContent[i].className.replace(" active", "");
                        }
                        
                        // Desativar todos os botões
                        tabButtons = document.getElementsByClassName("tab-button");
                        for (i = 0; i < tabButtons.length; i++) {
                            tabButtons[i].className = tabButtons[i].className.replace(" active", "");
                        }
                        
                        // Mostrar a aba atual e adicionar classe "active" ao botão
                        document.getElementById(tabName).className += " active";
                        evt.currentTarget.className += " active";
                    }
                </script>
            </body>
            </html>
            """)
        
        logger.info(f"Índice HTML gerado em: {html_path}")

def main():
    parser = argparse.ArgumentParser(description="Gerenciador de Metadados de Mídia")
    parser.add_argument("--directory", "-d", required=True, help="Diretório contendo os arquivos de mídia")
    parser.add_argument("--api-key", "-k", default=API_KEY, help="Chave da API do TMDB")
    parser.add_argument("--ffmpeg", "-f", help="Caminho para o executável do FFmpeg")
    args = parser.parse_args()
    
    manager = MediaMetadataManager(args.directory, args.api_key, args.ffmpeg)
    manager.scan_directory()
    manager.generate_html_index()
    
    logger.info("Processamento concluído!")

if __name__ == "__main__":
    main()
