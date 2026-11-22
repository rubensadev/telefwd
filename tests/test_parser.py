from pathlib import Path

from telefwd.parser import DefinitionParser


def test_divteam_parser_extracts_series_fields() -> None:
    parser = DefinitionParser(Path("telefwd/definitions/divteam.yaml"))
    text = """‼️**NUEVA SERIE**‼️
🎬 **Título:** __Pluribus__
📆 **Episodio:** __S01E07__
🔗 [__Pluribus S01E07 1080p__](https://example.com/torrent)"""

    message = parser.parse(text)

    assert message.category == "Serie"
    assert message.title == "Pluribus"
    assert message.episode == "S01E07"
    assert message.name == "Pluribus S01E07 1080p"
    assert message.torrent == "https://example.com/torrent"


def test_divteam_parser_extracts_year_and_unknown_category() -> None:
    parser = DefinitionParser(Path("telefwd/definitions/divteam.yaml"))

    movie = parser.parse(
        "NUEVA PELÍCULA\n🎬 **Título:** __Example__\n📆 **Año:** __2024__"
    )
    unknown = parser.parse("unrecognized message")

    assert movie.category == "Movie"
    assert movie.year == 2024
    assert unknown.category == "Unknown"


def test_nobs_parser_extracts_movie_metadata_and_button_urls() -> None:
    parser = DefinitionParser(Path("telefwd/definitions/nobs.yaml"))
    text = """🎬 Hermanastras 2026 1080p NF WEB-DL DUAL DD+ 5.1 Atmos x264-SPWEB
📂 Categoría: Movies
💾 Tamaño: 5.18 GiB
⭐ Calidad: WEB-DL
🎞 Codec: AVC
🔊 Audio: E-AC-3 JOC  🇬🇧 🇪🇸 🇷🇴
💬 Subs: 🇷🇴 🇬🇧 🇪🇸"""
    telegram_message = {
        "reply_markup": {
            "rows": [
                {
                    "buttons": [
                        {
                            "type": {
                                "url": "https://nobs.rawsmoke.net/torrents/15496"
                            }
                        },
                        {
                            "type": {
                                "url": "https://www.imdb.com/title/tt14413964"
                            }
                        },
                        {
                            "type": {
                                "url": "https://www.themoviedb.org/movie/1595124"
                            }
                        },
                    ]
                }
            ]
        }
    }

    message = parser.parse(text, telegram_message)

    assert message.category == "Movie"
    assert message.title == "Hermanastras"
    assert message.year == 2026
    assert message.size == "5.18 GiB"
    assert message.quality == "1080P"
    assert message.audio_languages == ["English", "Spanish", "Romanian"]
    assert message.subtitle_languages == ["Romanian", "English", "Spanish"]
    assert message.torrent == "https://nobs.rawsmoke.net/torrents/15496"
    assert message.imdb == "https://www.imdb.com/title/tt14413964"
    assert message.tmdb == "https://www.themoviedb.org/movie/1595124"


def test_torrentland_parser_extracts_tv_episode_metadata() -> None:
    parser = DefinitionParser(Path("telefwd/definitions/torrentland.yaml"))
    text = """Todas las de la ley S02E04 1080p DSN+ WEB-DL ESP-ENG DD+ 5.1 H.264

📺 Series -> WEB-DL
💾 1.4 GiB
👤 Bruszewski
🔗 Ficha"""
    telegram_message = {
        "entities": [
            {"url": "https://torrentland.li/torrents/91885"},
        ]
    }

    message = parser.parse(text, telegram_message)

    assert message.category == "Serie"
    assert message.title == "Todas las de la ley"
    assert message.season == 2
    assert message.episode == "S02E04"
    assert message.size == "1.4 GiB"
    assert message.quality == "1080P"
    assert message.source == "WEB-DL"
    assert message.codec == "H264"
    assert message.audio_languages == ["Spanish", "English"]
    assert message.torrent == "https://torrentland.li/torrents/91885"


def test_divteam_parser_extracts_rescued_season_pack() -> None:
    parser = DefinitionParser(Path("telefwd/definitions/divteam-ocio.yaml"))
    text = """♻ RESCUEDT - TORRENT RESCATADO
📚 G E O Más allá del límite (Miniserie) 2021 S01 1080p AMZN WEB-DL DD+ 5.1 H264 - TSeD

📂 Categoria: Pack Series
📦 Tamano: 24,55 GB
🌱 Seeders: 2

🔗 Ver torrent en DivTeam"""
    telegram_message = {
        "entities": [
            {"url": "https://divteam.li/details.php?id=35236"},
        ]
    }

    message = parser.parse(text, telegram_message)

    assert message.category == "Serie"
    assert message.title == "G E O Más allá del límite (Miniserie)"
    assert message.year == 2021
    assert message.season == 1
    assert message.episode == "S01"
    assert message.size == "24,55 GB"
    assert message.torrent == "https://divteam.li/details.php?id=35236"
