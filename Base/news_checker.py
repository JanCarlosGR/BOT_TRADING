"""
Módulo para verificar noticias económicas de alto impacto
Evita operar cuando hay noticias importantes próximas

Este módulo proporciona funciones reutilizables para:
- Obtener noticias económicas del calendario de Investing.com
- Verificar si hay noticias próximas que puedan afectar el trading
- Determinar si se puede operar en un momento dado
- Validar días operativos (excluyendo fines de semana y festivos)
- Obtener resúmenes de noticias diarias, semanales y mensuales

Todas las funciones trabajan con timezone de New York (America/New_York)
y filtran noticias de alto impacto (3 estrellas) por defecto.

Autor: Trading Bot System
Última actualización: Diciembre 2025
"""

import requests
from datetime import datetime, timedelta
import pytz
from typing import List, Dict, Optional
from bs4 import BeautifulSoup
import re
import time
import logging

# Configurar logger
logger = logging.getLogger(__name__)

# Configuración
HIGH_IMPACT = 3  # Nivel de impacto alto (3 estrellas)


def get_currency_from_symbol(symbol: str) -> tuple:
    """
    Convierte el símbolo de trading a las monedas base y cotizada
    
    Args:
        symbol: Símbolo de trading (ej: 'EURUSD', 'GBPUSD')
    
    Returns:
        tuple: (base_currency, quote_currency) o (None, None) si el formato es inválido
    
    Ejemplo:
        >>> get_currency_from_symbol('EURUSD')
        ('EUR', 'USD')
        >>> get_currency_from_symbol('GBPJPY')
        ('GBP', 'JPY')
    """
    if len(symbol) == 6:
        base = symbol[:3]
        quote = symbol[3:]
        return base, quote
    return None, None



def scrape_investing_calendar(
    symbol: str,
    month: int = None,
    year: int = None,
    hours_ahead: int = None,
    min_impact: int = HIGH_IMPACT,
    currencies: List[str] = None,
    week: Optional[str] = None,
) -> List[Dict]:
    """
    Hace scraping del calendario económico de Investing.com
    
    Args:
        symbol: Símbolo a verificar (ej: 'EURUSD')
        month: Mes (1-12). Si es None, usa el mes actual
        year: Año. Si es None, usa el año actual
        hours_ahead: Si se especifica, solo retorna noticias en las próximas X horas
        min_impact: Nivel mínimo de impacto (0-3). 0 = todos, 3 = solo alto impacto
        currencies: Lista de monedas a filtrar (ej: ['USD', 'EUR']). Si es None, usa base y quote del símbolo
    
    Returns:
        Lista de noticias encontradas
    """
    base, quote = get_currency_from_symbol(symbol)
    if not base or not quote:
        return []
    
    ny_tz = pytz.timezone('America/New_York')
    # Investing.com muestra las horas en GMT+1 (Europa Central)
    investing_tz = pytz.timezone('Europe/Paris')  # GMT+1 (o Europe/Madrid)
    now_ny = datetime.now(ny_tz)
    
    # Determinar el mes y año a consultar
    if month is None:
        month = now_ny.month
    if year is None:
        year = now_ny.year
    
    # Construir URL de Investing.com
    # Investing.com usa parámetros en la URL para filtrar
    url = "https://es.investing.com/economic-calendar/"
    params: Dict[str, str] = {}
    if week:
        params["week"] = week
    
    # Monedas relevantes - si se especifica currencies, usar esas, sino usar base y quote
    if currencies is not None:
        currencies_to_check = [c.upper() for c in currencies]  # Asegurar mayúsculas
    else:
        currencies_to_check = [base, quote, 'EU']  # EU para eventos de la UE
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://www.investing.com/',
        }

        # Intentar con reintentos
        max_retries = 3
        retry_delay = 2.0
        response = None
        
        for attempt in range(max_retries):
            try:
                response = requests.get(
                    url,
                    headers=headers,
                    params=params or None,
                    timeout=15,
                )
                response.raise_for_status()
                break  # Éxito, salir del loop
                
            except requests.exceptions.Timeout:
                if attempt < max_retries - 1:
                    logger.warning(f"Timeout al obtener noticias de Investing.com (intento {attempt + 1}/{max_retries}), reintentando...")
                    time.sleep(retry_delay)
                    continue
                logger.error("Timeout al obtener noticias de Investing.com después de múltiples intentos")
                raise
            except requests.exceptions.RequestException as e:
                if attempt < max_retries - 1:
                    logger.warning(f"Error al obtener noticias de Investing.com (intento {attempt + 1}/{max_retries}): {e}, reintentando...")
                    time.sleep(retry_delay)
                    continue
                logger.error(f"Error al obtener noticias de Investing.com: {e}")
                raise
        
        if response is None:
            raise requests.exceptions.RequestException("No se pudo obtener respuesta después de múltiples intentos")
        
        soup = BeautifulSoup(response.text, 'html.parser')
        news_list = []
        
        # Buscar la tabla del calendario por ID primero (más preciso)
        calendar_table = soup.find('table', id='economicCalendarData')
        
        # Si no se encuentra por ID, buscar por estructura de headers
        if not calendar_table:
            tables = soup.find_all('table')
            for table in tables:
                thead = table.find('thead')
                if thead:
                    headers_text = [th.get_text(strip=True) for th in thead.find_all('th')]
                    if 'Time' in headers_text and 'Event' in headers_text and 'Imp.' in headers_text:
                        calendar_table = table
                        break
        
        if not calendar_table:
            return []
        
        # Extraer eventos de las filas
        tbody = calendar_table.find('tbody')
        if not tbody:
            return []
        
        rows = tbody.find_all('tr')
        current_date_ny = None  # Para manejar separadores de día
        
        for row in rows:
            # Saltar filas separadoras de día (class="theDay")
            if 'theDay' in row.get('class', []):
                # Extraer la fecha del separador si es posible
                day_text = row.get_text(strip=True)
                handled_day = False
                try:
                    # Formato en inglés: "Sunday, November 2, 2025"
                    date_match = re.search(r'(\w+day),?\s+(\w+)\s+(\d+),?\s+(\d{4})', day_text)
                    if date_match:
                        month_names_en = {
                            'january': 1,
                            'february': 2,
                            'march': 3,
                            'april': 4,
                            'may': 5,
                            'june': 6,
                            'july': 7,
                            'august': 8,
                            'september': 9,
                            'october': 10,
                            'november': 11,
                            'december': 12,
                        }
                        month_str = date_match.group(2).lower()
                        day = int(date_match.group(3))
                        year = int(date_match.group(4))
                        month = month_names_en.get(month_str, now_ny.month)
                        current_date_ny = ny_tz.localize(datetime(year, month, day))
                        handled_day = True
                    if not handled_day:
                        # Formato en español: "Domingo, 2 de noviembre de 2025"
                        date_match_es = re.search(
                            r'([A-Za-zÁÉÍÓÚáéíóúñÑ]+),\s+(\d{1,2})\s+de\s+([A-Za-zÁÉÍÓÚáéíóúñÑ]+)\s+de\s+(\d{4})',
                            day_text,
                            re.IGNORECASE,
                        )
                        if date_match_es:
                            month_names_es = {
                                'enero': 1,
                                'febrero': 2,
                                'marzo': 3,
                                'abril': 4,
                                'mayo': 5,
                                'junio': 6,
                                'julio': 7,
                                'agosto': 8,
                                'septiembre': 9,
                                'setiembre': 9,
                                'octubre': 10,
                                'noviembre': 11,
                                'diciembre': 12,
                            }
                            month_str_es = date_match_es.group(3).lower()
                            day = int(date_match_es.group(2))
                            year = int(date_match_es.group(4))
                            month = month_names_es.get(month_str_es, now_ny.month)
                            current_date_ny = ny_tz.localize(datetime(year, month, day))
                            handled_day = True
                except Exception:
                    handled_day = False
                continue
            
            cells = row.find_all('td')
            if len(cells) < 4:
                continue
            
            # Verificar si es una fila de evento (debe tener class="js-event-item")
            if 'js-event-item' not in row.get('class', []):
                continue
            
            try:
                # Intentar obtener la fecha/hora del atributo data-event-datetime (más confiable)
                event_datetime_str = row.get('data-event-datetime', '')
                event_date = None
                
                if event_datetime_str:
                    try:
                        # Formato: "2025/11/02 16:45:00"
                        # Investing.com muestra las horas en GMT+1 (Europa Central)
                        event_date = datetime.strptime(event_datetime_str, '%Y/%m/%d %H:%M:%S')
                        # Primero localizar como GMT+1 (Europa Central)
                        event_date = investing_tz.localize(event_date.replace(tzinfo=None))
                        # Luego convertir a timezone NY
                        event_date = event_date.astimezone(ny_tz)
                    except Exception:
                        pass
                
                # Si no hay data-event-datetime, intentar parsear desde el texto de la hora
                time_str_full = None
                if not event_date:
                    time_text = cells[0].get_text(strip=True)
                    time_str_full = time_text
                    
                    if time_text and time_text != 'All Day':
                        try:
                            time_match = re.search(r'(\d{1,2}):(\d{2})', time_text)
                            if time_match:
                                hour = int(time_match.group(1))
                                minute = int(time_match.group(2))
                                
                                # Usar la fecha actual del separador o la fecha actual
                                # La hora mostrada en la página está en GMT+1, así que usamos esa zona horaria
                                base_date = current_date_ny if current_date_ny else now_ny
                                # Convertir la fecha base a GMT+1 para parsear la hora correctamente
                                base_date_gmt1 = base_date.astimezone(investing_tz)
                                event_date_gmt1 = base_date_gmt1.replace(hour=hour, minute=minute, second=0, microsecond=0)
                                
                                # Ajustar si la hora parece ser del día siguiente o anterior
                                if event_date_gmt1 < base_date_gmt1 - timedelta(hours=12):
                                    event_date_gmt1 = event_date_gmt1 + timedelta(days=1)
                                elif event_date_gmt1 > base_date_gmt1 + timedelta(days=1):
                                    event_date_gmt1 = event_date_gmt1 - timedelta(days=1)
                                
                                # Convertir de GMT+1 a NY
                                event_date = event_date_gmt1.astimezone(ny_tz)
                        except Exception:
                            pass
                    else:
                        # "All Day" - usar inicio del día
                        # La fecha mostrada está en GMT+1, convertir a NY
                        base_date = current_date_ny if current_date_ny else now_ny
                        base_date_gmt1 = base_date.astimezone(investing_tz)
                        event_date_gmt1 = base_date_gmt1.replace(hour=0, minute=0, second=0, microsecond=0)
                        event_date = event_date_gmt1.astimezone(ny_tz)
                
                # Si aún no se pudo parsear, usar hora actual
                if not event_date:
                    event_date = now_ny
                
                # Currency - extraer del texto o de span con clase ceFlags
                currency_cell = cells[1]
                currency_span = currency_cell.find('span', class_='ceFlags')
                if currency_span:
                    # El texto después del span suele ser la moneda
                    currency = currency_cell.get_text(strip=True)
                    # Extraer solo las letras mayúsculas (EUR, USD, etc.)
                    currency_match = re.search(r'\b([A-Z]{2,3})\b', currency)
                    if currency_match:
                        currency = currency_match.group(1)
                else:
                    currency = currency_cell.get_text(strip=True)
                
                # Verificar si es una moneda relevante
                if currency not in currencies_to_check:
                    continue
                
                # Impact - contar estrellas llenas (múltiples métodos de detección)
                impact_cell = cells[2]
                
                # Método 1: Buscar por clase específica (grayFullBullishIcon)
                impact_icons = impact_cell.find_all('i', class_='grayFullBullishIcon')
                
                # Método 2: Si no se encontraron, buscar cualquier ícono con clase que contenga "Bullish" o "Full"
                if not impact_icons:
                    impact_icons = impact_cell.find_all('i', class_=re.compile(r'.*[Bb]ullish.*|.*[Ff]ull.*'))
                
                # Método 3: Buscar por atributo title que contenga "star" o "estrella"
                if not impact_icons:
                    all_icons = impact_cell.find_all('i')
                    for icon in all_icons:
                        icon_title = icon.get('title', '').lower()
                        icon_class = ' '.join(icon.get('class', [])).lower()
                        if 'star' in icon_title or 'estrella' in icon_title or 'full' in icon_class:
                            impact_icons.append(icon)
                
                # Método 4: Buscar también en elementos <span> (algunos sitios usan spans para estrellas)
                if not impact_icons:
                    impact_icons = impact_cell.find_all('span', class_=re.compile(r'.*[Bb]ullish.*|.*[Ff]ull.*|.*[Ss]tar.*'))
                
                # Método 5: Contar estrellas por el número de íconos en la celda (fallback)
                if not impact_icons:
                    # Contar todos los íconos <i> y <span> en la celda que tengan clases
                    all_icons_in_cell = impact_cell.find_all(['i', 'span'])
                    impact_icons = [icon for icon in all_icons_in_cell if icon.get('class')]
                
                # Obtener texto de la celda de impacto para verificar holidays e inferir nivel
                impact_text = impact_cell.get_text(strip=True)
                is_holiday = 'Holiday' in impact_text or 'holiday' in impact_text.lower()
                
                # Método 6: Si aún no se encontraron, intentar inferir del texto de la celda
                impact_level = len(impact_icons)  # Número de estrellas llenas
                if impact_level == 0 and not is_holiday:
                    # Intentar inferir del texto (ej: "High", "Alto", "3", etc.)
                    impact_text_lower = impact_text.lower()
                    if 'high' in impact_text_lower or 'alto' in impact_text_lower:
                        impact_level = 3  # Asumir alto impacto si dice "high"
                    elif 'medium' in impact_text_lower or 'medio' in impact_text_lower:
                        impact_level = 2
                    elif 'low' in impact_text_lower or 'bajo' in impact_text_lower:
                        impact_level = 1
                    # Buscar números en el texto (ej: "3 stars", "3 estrellas")
                    number_match = re.search(r'(\d+)', impact_text)
                    if number_match:
                        impact_level = int(number_match.group(1))
                
                # Si es un holiday, marcarlo pero no filtrarlo (necesitamos saber qué días son festivos)
                if is_holiday:
                    # Holidays no tienen impacto de estrellas, pero los necesitamos para detectar días no operativos
                    pass
                else:
                    # Filtrar por nivel mínimo de impacto (solo para eventos económicos)
                    if impact_level < min_impact:
                        continue
                
                # Event
                event_link = cells[3].find('a')
                if event_link:
                    event_text = event_link.get_text(strip=True)
                else:
                    event_text = cells[3].get_text(strip=True)
                
                # Actual, Forecast, Previous
                actual = cells[4].get_text(strip=True) if len(cells) > 4 else ''
                forecast = cells[5].get_text(strip=True) if len(cells) > 5 else ''
                previous = cells[6].get_text(strip=True) if len(cells) > 6 else ''
                
                # Filtrar por horas_ahead si se especifica
                if hours_ahead is not None:
                    end_time = now_ny + timedelta(hours=hours_ahead)
                    if event_date > end_time:
                        continue
                
                # Formatear time_str si no se definió antes
                if time_str_full is None:
                    if event_date:
                        time_str_full = event_date.strftime('%Y-%m-%d %H:%M:%S %Z')
                    else:
                        time_text = cells[0].get_text(strip=True) if 'time_text' not in locals() else time_text
                        time_str_full = time_text if time_text else 'N/A'
                
                # Validación adicional: asegurar que solo se agreguen noticias de 3 estrellas (o holidays)
                if is_holiday or impact_level >= min_impact:
                    news_item = {
                        'time': event_date,
                        'time_str': time_str_full,
                        'currency': currency,
                        'title': event_text,
                        'impact': impact_level,
                        'impact_level': impact_level,  # Añadir también impact_level para consistencia
                        'is_holiday': is_holiday,
                        'actual': actual,
                        'forecast': forecast,
                        'previous': previous,
                    }
                    news_list.append(news_item)
                    # Logging para depuración (solo para noticias de alto impacto)
                    if impact_level >= 3 and not is_holiday:
                        logger.debug(f"Noticia detectada: {event_text} - {currency} - "
                                   f"Impacto: {impact_level} - Hora: {time_str_full}")
                
            except Exception as e:
                # Continuar con la siguiente fila si hay error
                continue
        
        # Ordenar por fecha
        news_list.sort(key=lambda x: x['time'])
        return news_list
        
    except requests.exceptions.RequestException as e:
        print(f"⚠️  Error de conexión al hacer scraping de Investing.com: {e}")
        return []
    except Exception as e:
        print(f"⚠️  Error al hacer scraping de Investing.com: {e}")
        return []


def check_high_impact_news_investing(symbol: str, hours_ahead: int = 2) -> List[Dict]:
    """
    Verifica noticias de alto impacto usando Investing.com Economic Calendar (web scraping)
    
    Args:
        symbol: Símbolo a verificar (ej: 'EURUSD')
        hours_ahead: Horas adelante para buscar noticias (default: 2)
    
    Returns:
        List[Dict]: Lista de noticias de alto impacto encontradas
    
    Nota:
        Esta función es un wrapper de `scrape_investing_calendar` con parámetros por defecto
        para facilitar el uso en estrategias.
    """
    return scrape_investing_calendar(symbol, hours_ahead=hours_ahead)


def check_high_impact_news_calendar(symbol: str, hours_ahead: int = 2) -> List[Dict]:
    """
    Verifica noticias de alto impacto usando únicamente Investing.com
    Solo retorna noticias PENDIENTES (futuras, no pasadas)
    
    Args:
        symbol: Símbolo a verificar (ej: 'EURUSD')
        hours_ahead: Horas adelante para buscar noticias (default: 2)
    
    Returns:
        List[Dict]: Lista de noticias de alto impacto PENDIENTES encontradas
    
    Nota:
        Esta función filtra automáticamente las noticias pasadas, mostrando solo
        las que están pendientes (futuras).
    """
    news_list = check_high_impact_news_investing(symbol, hours_ahead)
    
    # Filtrar solo noticias PENDIENTES (futuras)
    ny_tz = pytz.timezone('America/New_York')
    now_ny = datetime.now(ny_tz)
    pending_news = []
    
    for news in news_list:
        news_time = news.get('time')
        if isinstance(news_time, datetime):
            if news_time.tzinfo is None:
                news_time_ny = ny_tz.localize(news_time)
            else:
                news_time_ny = news_time.astimezone(ny_tz)
            # Solo incluir si la noticia es futura
            if news_time_ny > now_ny:
                pending_news.append(news)
        elif isinstance(news_time, str):
            try:
                news_time_parsed = datetime.fromisoformat(news_time.replace('Z', '+00:00'))
                if news_time_parsed.tzinfo is None:
                    news_time_parsed = pytz.utc.localize(news_time_parsed)
                news_time_ny = news_time_parsed.astimezone(ny_tz)
                if news_time_ny > now_ny:
                    pending_news.append(news)
            except:
                pass
    
    return pending_news


def get_monthly_news(symbol: str, month: int = None, year: int = None) -> List[Dict]:
    """
    Obtiene todas las noticias de alto impacto del mes para un símbolo
    Solo retorna noticias PENDIENTES (futuras, no pasadas)

    Args:
        symbol: Símbolo a verificar (ej: 'EURUSD')
        month: Mes (1-12). Si es None, usa el mes actual
        year: Año. Si es None, usa el año actual

    Returns:
        Lista de noticias de alto impacto PENDIENTES del mes ordenadas por fecha
    """
    # Obtener todas las noticias del mes
    all_news = scrape_investing_calendar(symbol, month, year)
    
    # Filtrar solo noticias PENDIENTES (futuras)
    ny_tz = pytz.timezone('America/New_York')
    now_ny = datetime.now(ny_tz)
    pending_news = []
    
    for news in all_news:
        news_time = news.get('time')
        if isinstance(news_time, datetime):
            if news_time.tzinfo is None:
                news_time_ny = ny_tz.localize(news_time)
            else:
                news_time_ny = news_time.astimezone(ny_tz)
            # Solo incluir si la noticia es futura
            if news_time_ny > now_ny:
                pending_news.append(news)
        elif isinstance(news_time, str):
            try:
                news_time_parsed = datetime.fromisoformat(news_time.replace('Z', '+00:00'))
                if news_time_parsed.tzinfo is None:
                    news_time_parsed = pytz.utc.localize(news_time_parsed)
                news_time_ny = news_time_parsed.astimezone(ny_tz)
                if news_time_ny > now_ny:
                    pending_news.append(news)
            except:
                pass
    
    # Ordenar por fecha
    pending_news.sort(key=lambda x: x.get('time', datetime.min))
    return pending_news


def get_weekly_news(
    symbol: str,
    min_impact: int = 3,
    currencies: List[str] = None,
    week: str = "current",
) -> List[Dict]:
    """
    Obtiene todas las noticias de esta semana (lunes a domingo) para un símbolo
    Solo retorna noticias PENDIENTES (futuras, no pasadas)

    Args:
        symbol: Símbolo a verificar (ej: 'EURUSD')
        min_impact: Nivel mínimo de impacto (0-3). Por defecto 3 = solo alto impacto
        currencies: Lista de monedas a filtrar (ej: ['USD', 'EUR']). Si es None, usa solo USD y EUR
        week: Semana a consultar: 'previous', 'current' o 'next'

    Returns:
        Lista de noticias PENDIENTES de esta semana ordenadas por fecha
    """
    base, quote = get_currency_from_symbol(symbol)
    if not base or not quote:
        return []

    ny_tz = pytz.timezone('America/New_York')
    now_ny = datetime.now(ny_tz)

    # Configurar filtro de monedas
    if currencies is None:
        currencies = ['USD', 'EUR']
    
    # Determinar semana objetivo
    week_lower = (week or "current").lower()
    week_param = None
    week_offset = 0
    if week_lower in {"next", "proxima", "próxima", "next_week"}:
        week_param = "next"
        week_offset = 1
    elif week_lower in {"previous", "prev", "anterior", "last"}:
        week_param = "prev"
        week_offset = -1
    
    news_list = scrape_investing_calendar(
        symbol,
        min_impact=min_impact,
        currencies=currencies,
        week=week_param,
    )
    
    # Calcular rango de la semana seleccionada
    days_since_monday = now_ny.weekday()
    base_week_start = (now_ny - timedelta(days=days_since_monday)).replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = base_week_start + timedelta(days=week_offset * 7)
    week_end = (week_start + timedelta(days=6)).replace(hour=23, minute=59, second=59, microsecond=999999)
    
    # Filtrar solo noticias PENDIENTES (futuras) dentro del rango de la semana
    now_ny = datetime.now(ny_tz)
    weekly_news = []
    for news in news_list:
        news_time = news.get('time')
        if news_time is None:
            continue
        try:
            if isinstance(news_time, str):
                parsed = datetime.fromisoformat(news_time.replace('Z', '+00:00'))
                if parsed.tzinfo is None:
                    parsed = pytz.utc.localize(parsed)
                news_time_dt = parsed.astimezone(ny_tz)
            elif isinstance(news_time, datetime):
                if news_time.tzinfo is None:
                    news_time_dt = ny_tz.localize(news_time)
                else:
                    news_time_dt = news_time.astimezone(ny_tz)
            else:
                continue
        except Exception:
            continue
        
        # Solo incluir si está en el rango de la semana Y es futura (pendiente)
        if week_start <= news_time_dt <= week_end and news_time_dt > now_ny:
            weekly_news.append(news)
    
    weekly_news.sort(key=lambda x: x.get('time', datetime.min))
    return weekly_news


def has_high_impact_news_soon(symbol: str, minutes_before: int = 30, hours_ahead: int = 2) -> tuple:
    """
    Verifica si hay noticias de alto impacto próximas que afecten al símbolo
    
    Args:
        symbol: Símbolo a verificar (ej: 'EURUSD')
        minutes_before: Minutos antes de la noticia para considerar "próxima" (default: 30)
        hours_ahead: Horas adelante para verificar (default: 2)
    
    Returns:
        tuple: (bool, List[Dict]) - (hay_noticia_próxima, lista_noticias)
    
    Nota:
        Esta función es útil para verificación rápida, pero se recomienda usar
        `can_trade_now()` para decisiones de trading más precisas.
    """
    base, quote = get_currency_from_symbol(symbol)
    if not base or not quote:
        return False, []
    
    ny_tz = pytz.timezone('America/New_York')
    now_ny = datetime.now(ny_tz)
    
    # Verificar noticias
    news_list = check_high_impact_news_calendar(symbol, hours_ahead)
    
    if not news_list:
        return False, []
    
    # Filtrar noticias que están dentro del rango de tiempo
    relevant_news = []
    time_threshold = now_ny + timedelta(minutes=minutes_before)
    time_limit = now_ny + timedelta(hours=hours_ahead)
    
    for news in news_list:
        try:
            news_time = news.get('time')
            # Manejar datetime directamente (formato retornado por scrape_investing_calendar)
            if isinstance(news_time, datetime):
                if news_time.tzinfo is None:
                    news_time_ny = ny_tz.localize(news_time)
                else:
                    news_time_ny = news_time.astimezone(ny_tz)
            elif isinstance(news_time, str):
                # Parsear string si viene en formato ISO
                news_time = datetime.fromisoformat(news_time.replace('Z', '+00:00'))
                if news_time.tzinfo is None:
                    news_time = pytz.utc.localize(news_time)
                news_time_ny = news_time.astimezone(ny_tz)
            else:
                continue
            
            # Verificar si la noticia está dentro del rango
            if time_threshold <= news_time_ny <= time_limit:
                relevant_news.append(news)
        except Exception as e:
            logger.warning(f"Error al procesar tiempo de noticia: {e}")
            continue
    
    has_news = len(relevant_news) > 0
    return has_news, relevant_news


def can_trade_now(symbol: str, minutes_before: int = 5, minutes_after: int = 5, check_consecutive: bool = True) -> tuple:
    """
    Determina si se puede operar en este momento basado en las noticias
    
    Reglas:
    - No operar 5 minutos antes de una noticia
    - Después de una noticia, esperar 5 minutos para ver si viene otra consecutiva
    - Si no viene otra noticia en esos 5 minutos, se puede operar
    - Si viene otra noticia consecutiva, seguir esperando
    
    Args:
        symbol: Símbolo a verificar (ej: 'EURUSD')
        minutes_before: Minutos antes de la noticia para evitar operar (default: 5)
        minutes_after: Minutos después de la noticia para verificar consecutivas (default: 5)
        check_consecutive: Si True, verifica noticias consecutivas (default: True)
    
    Returns:
        tuple: (can_trade: bool, reason: str, next_news: Dict or None)
    """
    base, quote = get_currency_from_symbol(symbol)
    if not base or not quote:
        return True, "Sin símbolo válido", None
    
    ny_tz = pytz.timezone('America/New_York')
    now_ny = datetime.now(ny_tz)
    
    # Obtener todas las noticias de hoy y próximas horas (para USD/EUR, 3 estrellas)
    all_news = scrape_investing_calendar(symbol, min_impact=3, currencies=['USD', 'EUR'], hours_ahead=24)
    
    # Logging para depuración
    logger.debug(f"[{symbol}] Scraping de noticias: {len(all_news) if all_news else 0} noticias encontradas")
    if all_news:
        logger.debug(f"[{symbol}] Primeras noticias encontradas:")
        for i, news in enumerate(all_news[:5]):  # Mostrar primeras 5
            logger.debug(f"  {i+1}. {news.get('title', 'N/A')} - {news.get('currency', 'N/A')} - "
                        f"Impacto: {news.get('impact_level', news.get('impact', 0))} - "
                        f"Hora: {news.get('time_str', 'N/A')}")
    
    if not all_news:
        logger.debug(f"[{symbol}] No se encontraron noticias en el scraping. Verificando conexión y estructura HTML...")
        return True, "No hay noticias de alto impacto próximas", None
    
    # Filtrar noticias relevantes (hoy y próximas 24 horas) - SOLO 3 ESTRELLAS
    relevant_news = []
    filtered_count = 0
    for news in all_news:
        try:
            # Validar que sea de 3 estrellas (no holidays)
            is_holiday = news.get('is_holiday', False)
            impact = news.get('impact', 0)
            impact_level = news.get('impact_level', impact)
            
            # Solo incluir noticias de 3 estrellas (excluir holidays)
            if is_holiday or impact_level < 3:
                filtered_count += 1
                logger.debug(f"[{symbol}] Noticia filtrada: {news.get('title', 'N/A')} - "
                           f"Impacto: {impact_level}, Holiday: {is_holiday}")
                continue
            
            news_time = news.get('time')
            if isinstance(news_time, str):
                news_time = datetime.fromisoformat(news_time.replace('Z', '+00:00'))
                if news_time.tzinfo is None:
                    news_time = pytz.utc.localize(news_time)
                news_time = news_time.astimezone(ny_tz)
            
            # Solo noticias de hoy en adelante
            if news_time >= now_ny.replace(hour=0, minute=0, second=0, microsecond=0):
                relevant_news.append({
                    'time': news_time,
                    'title': news.get('title', 'Sin título'),
                    'currency': news.get('currency', 'N/A'),
                    'impact_level': impact_level  # Incluir nivel de impacto
                })
        except Exception as e:
            logger.debug(f"[{symbol}] Error al procesar noticia: {e}")
            continue
    
    # Logging del resumen de filtrado
    logger.debug(f"[{symbol}] Resumen de filtrado: {len(all_news)} noticias totales, "
                f"{filtered_count} filtradas (impacto < 3 o holiday), "
                f"{len(relevant_news)} noticias relevantes (3 estrellas, futuras)")
    
    if not relevant_news:
        logger.debug(f"[{symbol}] No hay noticias relevantes después del filtrado")
        return True, "No hay noticias de alto impacto próximas", None
    
    # Ordenar por tiempo
    relevant_news.sort(key=lambda x: x['time'])
    
    # Verificar si estamos dentro del período de bloqueo antes de una noticia
    for news in relevant_news:
        news_time = news['time']
        time_before_news = news_time - timedelta(minutes=minutes_before)
        
        # Si estamos dentro del período de bloqueo antes de la noticia
        if now_ny >= time_before_news and now_ny < news_time:
            time_until_news = (news_time - now_ny).total_seconds() / 60
            return False, f"Bloqueado: Noticia en {time_until_news:.1f} minutos ({news['title']})", news
        
        # Si la noticia ya pasó, verificar si estamos en el período de espera post-noticia
        if now_ny >= news_time:
            time_after_news = (now_ny - news_time).total_seconds() / 60
            
            # Si estamos dentro del período de espera post-noticia
            if time_after_news <= minutes_after:
                # Verificar si hay otra noticia consecutiva
                if check_consecutive:
                    # Buscar la siguiente noticia
                    next_news = None
                    for n in relevant_news:
                        if n['time'] > news_time:
                            next_news = n
                            break
                    
                    if next_news:
                        time_until_next = (next_news['time'] - news_time).total_seconds() / 60
                        # Si la siguiente noticia está muy cerca (dentro de 30 minutos), considerar consecutiva
                        if time_until_next <= 30:
                            return False, f"Bloqueado: Noticia consecutiva en {time_until_next:.1f} minutos ({next_news['title']})", next_news
                
                # Si no hay noticia consecutiva, estamos en período de espera
                remaining_wait = minutes_after - time_after_news
                if remaining_wait > 0:
                    return False, f"Esperando {remaining_wait:.1f} minutos después de noticia ({news['title']})", news
                # Si ya pasó el tiempo de espera, se puede operar
    
    # Si no estamos en ningún período de bloqueo
    # Verificar la próxima noticia para informar
    next_news = None
    for news in relevant_news:
        if news['time'] > now_ny:
            next_news = news
            break
    
    if next_news:
        time_until_next = (next_news['time'] - now_ny).total_seconds() / 60
        return True, f"Próxima noticia en {time_until_next:.1f} minutos", next_news
    
    return True, "No hay noticias próximas", None


def validate_trading_day(date: datetime = None) -> tuple:
    """
    Valida si un día es operativo (no es fin de semana ni día festivo)
    
    Args:
        date: Fecha a validar. Si es None, usa la fecha actual
    
    Returns:
        tuple: (is_trading_day: bool, reason: str, holidays: List[Dict])
    """
    ny_tz = pytz.timezone('America/New_York')
    if date is None:
        date = datetime.now(ny_tz)
    elif date.tzinfo is None:
        date = ny_tz.localize(date)
    else:
        date = date.astimezone(ny_tz)
    
    # Verificar si es fin de semana
    if date.weekday() >= 5:  # 5 = sábado, 6 = domingo
        return False, f"Día no operativo: {date.strftime('%A')} (fin de semana)", []
    
    # Verificar si es día festivo (para USD/EUR)
    # Obtener holidays del día
    all_events = scrape_investing_calendar('EURUSD', month=date.month, year=date.year, min_impact=0, currencies=['USD', 'EUR'])
    
    day_holidays = []
    day_key = date.strftime('%Y-%m-%d')
    
    for event in all_events:
        if event.get('is_holiday', False):
            try:
                event_time = event.get('time')
                if isinstance(event_time, str):
                    event_time = datetime.fromisoformat(event_time.replace('Z', '+00:00'))
                if isinstance(event_time, datetime):
                    if event_time.tzinfo is None:
                        event_time = ny_tz.localize(event_time)
                    else:
                        event_time = event_time.astimezone(ny_tz)
                    
                    if event_time.strftime('%Y-%m-%d') == day_key:
                        day_holidays.append(event)
            except:
                pass
    
    if day_holidays:
        holiday_names = [h.get('title', 'Holiday') for h in day_holidays]
        holiday_text = ', '.join(holiday_names)
        return False, f"Día no operativo: Día festivo - {holiday_text}", day_holidays
    
    return True, f"Día operativo: {date.strftime('%A, %B %d, %Y')}", []


def get_daily_news_summary(symbol: str, date: datetime = None) -> str:
    """
    Obtiene un resumen de noticias del día
    Solo incluye noticias PENDIENTES (futuras, no pasadas) dentro del horario de trading (9 AM - 3 PM NY)
    
    Args:
        symbol: Símbolo a verificar (ej: 'EURUSD')
        date: Fecha. Si es None, usa hoy
    
    Returns:
        str: Resumen de noticias PENDIENTES del día
    """
    ny_tz = pytz.timezone('America/New_York')
    if date is None:
        date = datetime.now(ny_tz)
    elif date.tzinfo is None:
        date = ny_tz.localize(date)
    else:
        date = date.astimezone(ny_tz)
    
    # Obtener noticias del día (USD/EUR, 3 estrellas)
    all_news = scrape_investing_calendar(symbol, month=date.month, year=date.year, min_impact=3, currencies=['USD', 'EUR'])
    
    day_news = []
    day_key = date.strftime('%Y-%m-%d')
    
    # Definir horario de trading: 9:00 AM - 1:00 PM NY
    trading_start = date.replace(hour=9, minute=0, second=0, microsecond=0)
    trading_end = date.replace(hour=13, minute=0, second=0, microsecond=0)
    # Incluir noticias importantes hasta las 3 PM (ej: FOMC a las 2 PM)
    extended_end = date.replace(hour=15, minute=0, second=0, microsecond=0)
    
    for news in all_news:
        try:
            news_time = news.get('time')
            if isinstance(news_time, str):
                news_time = datetime.fromisoformat(news_time.replace('Z', '+00:00'))
            if isinstance(news_time, datetime):
                if news_time.tzinfo is None:
                    news_time = ny_tz.localize(news_time)
                else:
                    news_time = news_time.astimezone(ny_tz)
                
                # Verificar que sea del día correcto
                if news_time.strftime('%Y-%m-%d') == day_key:
                    # Incluir noticias:
                    # 1. Antes del horario de trading (para mostrar qué viene)
                    # 2. Dentro del horario de trading (9 AM - 1 PM NY)
                    # 3. Después de la 1 PM pero antes de las 3 PM (noticias importantes como FOMC)
                    if news_time < trading_start:
                        # Noticia antes del horario de trading - incluir para información
                        day_news.append(news)
                    elif trading_start <= news_time <= trading_end:
                        # Noticia dentro del horario de trading - incluir
                        day_news.append(news)
                    elif trading_end < news_time <= extended_end:
                        # Noticia después de la 1 PM pero antes de las 3 PM - incluir (ej: FOMC a las 2 PM)
                        day_news.append(news)
                    # Excluir noticias después de las 3 PM del mismo día
        except:
            pass
    
    if not day_news:
        return f"📅 {date.strftime('%A, %B %d, %Y')}: No hay noticias de alto impacto programadas"
    
    # Filtrar solo noticias de 3 estrellas (excluir holidays y noticias de menor impacto)
    # Y solo noticias PENDIENTES (futuras, no pasadas)
    now_ny = datetime.now(ny_tz)
    high_impact_news = []
    for news in day_news:
        impact = news.get('impact', 0)
        impact_level = news.get('impact_level', impact)
        is_holiday = news.get('is_holiday', False)
        
        # Solo incluir noticias de 3 estrellas (no holidays)
        if not is_holiday and impact_level >= 3:
            # Verificar que la noticia sea FUTURA (pendiente)
            news_time = news.get('time')
            if isinstance(news_time, datetime):
                if news_time.tzinfo is None:
                    news_time_ny = ny_tz.localize(news_time)
                else:
                    news_time_ny = news_time.astimezone(ny_tz)
                # Solo incluir si la noticia es futura
                if news_time_ny > now_ny:
                    high_impact_news.append(news)
            elif isinstance(news_time, str):
                try:
                    news_time_parsed = datetime.fromisoformat(news_time.replace('Z', '+00:00'))
                    if news_time_parsed.tzinfo is None:
                        news_time_parsed = pytz.utc.localize(news_time_parsed)
                    news_time_ny = news_time_parsed.astimezone(ny_tz)
                    if news_time_ny > now_ny:
                        high_impact_news.append(news)
                except:
                    pass
    
    if not high_impact_news:
        return f"📅 {date.strftime('%A, %B %d, %Y')}: No hay noticias de alto impacto (3 estrellas) pendientes"
    
    # Zona horaria de La Paz (UTC-4) para mostrar al usuario
    la_paz_tz = pytz.timezone('America/La_Paz')
    date_la_paz = date.astimezone(la_paz_tz)
    lines = [f"📅 {date_la_paz.strftime('%A, %B %d, %Y')}: {len(high_impact_news)} noticia(s) de alto impacto (3⭐) pendiente(s):"]
    for news in sorted(high_impact_news, key=lambda x: x.get('time', datetime.min)):
        news_time = news.get('time')
        if isinstance(news_time, datetime):
            # Convertir a La Paz para mostrar
            if news_time.tzinfo is None:
                news_time = ny_tz.localize(news_time)
            else:
                news_time = news_time.astimezone(ny_tz)
            news_time_la_paz = news_time.astimezone(la_paz_tz)
            time_str = news_time_la_paz.strftime('%H:%M')
        else:
            time_str = str(news_time)[:5] if news_time else 'N/A'
        
        impact_level = news.get('impact_level', news.get('impact', 0))
        stars = '⭐' * impact_level if impact_level > 0 else ''
        
        lines.append(f"  ⏰ {time_str} | {news.get('currency', 'N/A')} | {stars} {news.get('title', 'Sin título')}")
    
    return "\n".join(lines)


def get_daily_news_list(symbol: str, date: datetime = None) -> List[Dict]:
    """
    Obtiene la lista de noticias del día (útil para notificaciones)
    Solo incluye noticias PENDIENTES (futuras, no pasadas) dentro del horario de trading (9 AM - 3 PM NY)
    
    Args:
        symbol: Símbolo a verificar (ej: 'EURUSD')
        date: Fecha. Si es None, usa hoy
    
    Returns:
        List[Dict]: Lista de diccionarios con información de noticias PENDIENTES de alto impacto
    """
    ny_tz = pytz.timezone('America/New_York')
    if date is None:
        date = datetime.now(ny_tz)
    elif date.tzinfo is None:
        date = ny_tz.localize(date)
    else:
        date = date.astimezone(ny_tz)
    
    # Obtener noticias del día (USD/EUR, 3 estrellas)
    all_news = scrape_investing_calendar(symbol, month=date.month, year=date.year, min_impact=3, currencies=['USD', 'EUR'])
    
    day_news = []
    day_key = date.strftime('%Y-%m-%d')
    
    # Definir horario de trading: 9:00 AM - 1:00 PM NY
    trading_start = date.replace(hour=9, minute=0, second=0, microsecond=0)
    trading_end = date.replace(hour=13, minute=0, second=0, microsecond=0)
    # Incluir noticias importantes hasta las 3 PM (ej: FOMC a las 2 PM)
    extended_end = date.replace(hour=15, minute=0, second=0, microsecond=0)
    
    for news in all_news:
        try:
            news_time = news.get('time')
            if isinstance(news_time, str):
                news_time = datetime.fromisoformat(news_time.replace('Z', '+00:00'))
            if isinstance(news_time, datetime):
                if news_time.tzinfo is None:
                    news_time = ny_tz.localize(news_time)
                else:
                    news_time = news_time.astimezone(ny_tz)
                
                # Verificar que sea del día correcto
                if news_time.strftime('%Y-%m-%d') == day_key:
                    # Incluir noticias:
                    # 1. Antes del horario de trading (para mostrar qué viene)
                    # 2. Dentro del horario de trading (9 AM - 1 PM NY)
                    # 3. Después de la 1 PM pero antes de las 3 PM (noticias importantes como FOMC)
                    if news_time < trading_start:
                        # Noticia antes del horario de trading - incluir para información
                        day_news.append(news)
                    elif trading_start <= news_time <= trading_end:
                        # Noticia dentro del horario de trading - incluir
                        day_news.append(news)
                    elif trading_end < news_time <= extended_end:
                        # Noticia después de la 1 PM pero antes de las 3 PM - incluir (ej: FOMC a las 2 PM)
                        day_news.append(news)
                    # Excluir noticias después de las 3 PM del mismo día
        except:
            pass
    
    # Filtrar solo noticias de 3 estrellas (excluir holidays y noticias de menor impacto)
    # Y solo noticias PENDIENTES (futuras, no pasadas)
    now_ny = datetime.now(ny_tz)
    high_impact_news = []
    for news in day_news:
        impact = news.get('impact', 0)
        impact_level = news.get('impact_level', impact)
        is_holiday = news.get('is_holiday', False)
        
        # Solo incluir noticias de 3 estrellas (no holidays)
        if not is_holiday and impact_level >= 3:
            # Verificar que la noticia sea FUTURA (pendiente)
            news_time = news.get('time')
            if isinstance(news_time, datetime):
                if news_time.tzinfo is None:
                    news_time_ny = ny_tz.localize(news_time)
                else:
                    news_time_ny = news_time.astimezone(ny_tz)
                # Solo incluir si la noticia es futura
                if news_time_ny > now_ny:
                    high_impact_news.append(news)
            elif isinstance(news_time, str):
                try:
                    news_time_parsed = datetime.fromisoformat(news_time.replace('Z', '+00:00'))
                    if news_time_parsed.tzinfo is None:
                        news_time_parsed = pytz.utc.localize(news_time_parsed)
                    news_time_ny = news_time_parsed.astimezone(ny_tz)
                    if news_time_ny > now_ny:
                        high_impact_news.append(news)
                except:
                    pass
    
    # Ordenar por hora
    high_impact_news.sort(key=lambda x: x.get('time', datetime.min))
    
    return high_impact_news


def get_news_warning_message(symbol: str, news_list: List[Dict]) -> str:
    """
    Genera un mensaje de advertencia formateado sobre noticias próximas
    
    Args:
        symbol: Símbolo de trading (ej: 'EURUSD')
        news_list: Lista de diccionarios con información de noticias
    
    Returns:
        str: Mensaje de advertencia formateado, o cadena vacía si no hay noticias
    
    Ejemplo:
        >>> news = [{'title': 'NFP', 'currency': 'USD', 'time': '2025-12-08 08:30:00', 'impact': 3}]
        >>> msg = get_news_warning_message('EURUSD', news)
        >>> print(msg)
        ⚠️  ADVERTENCIA: Noticias de alto impacto próximas para EURUSD
        ============================================================
        📰 NFP
           Moneda: USD
           Hora: 2025-12-08 08:30:00
           Impacto: 3
        ...
    """
    if not news_list:
        return ""
    
    base, quote = get_currency_from_symbol(symbol)
    messages = []
    
    messages.append(f"\n⚠️  ADVERTENCIA: Noticias de alto impacto próximas para {symbol}")
    messages.append("=" * 60)
    
    for news in news_list:
        messages.append(f"📰 {news.get('title', 'Sin título')}")
        messages.append(f"   Moneda: {news.get('currency', 'N/A')}")
        messages.append(f"   Hora: {news.get('time', 'N/A')}")
        messages.append(f"   Impacto: {news.get('impact', 'Alto')}")
        messages.append("")
    
    messages.append("❌ OPERACIÓN BLOQUEADA: Evitando operar cerca de noticias importantes")
    
    return "\n".join(messages)
