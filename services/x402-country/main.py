from __future__ import annotations
import os, time
import uvicorn
from fastapi import FastAPI, Request, Query
from fastapi.responses import JSONResponse
from typing import Optional

PRICE_ATOMIC = os.getenv("PRICE_ATOMIC", "500")
PAY_TO = os.getenv("PAY_TO", "0x6458941857a70C6cA18c440a316035A21901A12b")
NETWORK = os.getenv("NETWORK", "base")
ASSET_ADDRESS = os.getenv("ASSET_ADDRESS", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")

stats = {"total_paid": 0, "revenue_usdc": 0.0, "start_time": time.time()}
app = FastAPI(title="x402 Country", version="1.0.0")

# iso2, iso3, name_en, name_fr, capital, continent, currency, dial_code, flag_emoji, tld
COUNTRIES = [
    {"iso2": "AD", "iso3": "AND", "name_en": "Andorra", "name_fr": "Andorre", "capital": "Andorra la Vella", "continent": "Europe", "currency": "EUR", "dial_code": "+376", "flag": "🇦🇩", "tld": ".ad"},
    {"iso2": "AE", "iso3": "ARE", "name_en": "United Arab Emirates", "name_fr": "Émirats arabes unis", "capital": "Abu Dhabi", "continent": "Asia", "currency": "AED", "dial_code": "+971", "flag": "🇦🇪", "tld": ".ae"},
    {"iso2": "AF", "iso3": "AFG", "name_en": "Afghanistan", "name_fr": "Afghanistan", "capital": "Kabul", "continent": "Asia", "currency": "AFN", "dial_code": "+93", "flag": "🇦🇫", "tld": ".af"},
    {"iso2": "AG", "iso3": "ATG", "name_en": "Antigua and Barbuda", "name_fr": "Antigua-et-Barbuda", "capital": "Saint John's", "continent": "Americas", "currency": "XCD", "dial_code": "+1-268", "flag": "🇦🇬", "tld": ".ag"},
    {"iso2": "AL", "iso3": "ALB", "name_en": "Albania", "name_fr": "Albanie", "capital": "Tirana", "continent": "Europe", "currency": "ALL", "dial_code": "+355", "flag": "🇦🇱", "tld": ".al"},
    {"iso2": "AM", "iso3": "ARM", "name_en": "Armenia", "name_fr": "Arménie", "capital": "Yerevan", "continent": "Asia", "currency": "AMD", "dial_code": "+374", "flag": "🇦🇲", "tld": ".am"},
    {"iso2": "AO", "iso3": "AGO", "name_en": "Angola", "name_fr": "Angola", "capital": "Luanda", "continent": "Africa", "currency": "AOA", "dial_code": "+244", "flag": "🇦🇴", "tld": ".ao"},
    {"iso2": "AR", "iso3": "ARG", "name_en": "Argentina", "name_fr": "Argentine", "capital": "Buenos Aires", "continent": "Americas", "currency": "ARS", "dial_code": "+54", "flag": "🇦🇷", "tld": ".ar"},
    {"iso2": "AT", "iso3": "AUT", "name_en": "Austria", "name_fr": "Autriche", "capital": "Vienna", "continent": "Europe", "currency": "EUR", "dial_code": "+43", "flag": "🇦🇹", "tld": ".at"},
    {"iso2": "AU", "iso3": "AUS", "name_en": "Australia", "name_fr": "Australie", "capital": "Canberra", "continent": "Oceania", "currency": "AUD", "dial_code": "+61", "flag": "🇦🇺", "tld": ".au"},
    {"iso2": "AZ", "iso3": "AZE", "name_en": "Azerbaijan", "name_fr": "Azerbaïdjan", "capital": "Baku", "continent": "Asia", "currency": "AZN", "dial_code": "+994", "flag": "🇦🇿", "tld": ".az"},
    {"iso2": "BA", "iso3": "BIH", "name_en": "Bosnia and Herzegovina", "name_fr": "Bosnie-Herzégovine", "capital": "Sarajevo", "continent": "Europe", "currency": "BAM", "dial_code": "+387", "flag": "🇧🇦", "tld": ".ba"},
    {"iso2": "BD", "iso3": "BGD", "name_en": "Bangladesh", "name_fr": "Bangladesh", "capital": "Dhaka", "continent": "Asia", "currency": "BDT", "dial_code": "+880", "flag": "🇧🇩", "tld": ".bd"},
    {"iso2": "BE", "iso3": "BEL", "name_en": "Belgium", "name_fr": "Belgique", "capital": "Brussels", "continent": "Europe", "currency": "EUR", "dial_code": "+32", "flag": "🇧🇪", "tld": ".be"},
    {"iso2": "BF", "iso3": "BFA", "name_en": "Burkina Faso", "name_fr": "Burkina Faso", "capital": "Ouagadougou", "continent": "Africa", "currency": "XOF", "dial_code": "+226", "flag": "🇧🇫", "tld": ".bf"},
    {"iso2": "BG", "iso3": "BGR", "name_en": "Bulgaria", "name_fr": "Bulgarie", "capital": "Sofia", "continent": "Europe", "currency": "BGN", "dial_code": "+359", "flag": "🇧🇬", "tld": ".bg"},
    {"iso2": "BH", "iso3": "BHR", "name_en": "Bahrain", "name_fr": "Bahreïn", "capital": "Manama", "continent": "Asia", "currency": "BHD", "dial_code": "+973", "flag": "🇧🇭", "tld": ".bh"},
    {"iso2": "BI", "iso3": "BDI", "name_en": "Burundi", "name_fr": "Burundi", "capital": "Gitega", "continent": "Africa", "currency": "BIF", "dial_code": "+257", "flag": "🇧🇮", "tld": ".bi"},
    {"iso2": "BJ", "iso3": "BEN", "name_en": "Benin", "name_fr": "Bénin", "capital": "Porto-Novo", "continent": "Africa", "currency": "XOF", "dial_code": "+229", "flag": "🇧🇯", "tld": ".bj"},
    {"iso2": "BN", "iso3": "BRN", "name_en": "Brunei", "name_fr": "Brunéi", "capital": "Bandar Seri Begawan", "continent": "Asia", "currency": "BND", "dial_code": "+673", "flag": "🇧🇳", "tld": ".bn"},
    {"iso2": "BO", "iso3": "BOL", "name_en": "Bolivia", "name_fr": "Bolivie", "capital": "Sucre", "continent": "Americas", "currency": "BOB", "dial_code": "+591", "flag": "🇧🇴", "tld": ".bo"},
    {"iso2": "BR", "iso3": "BRA", "name_en": "Brazil", "name_fr": "Brésil", "capital": "Brasilia", "continent": "Americas", "currency": "BRL", "dial_code": "+55", "flag": "🇧🇷", "tld": ".br"},
    {"iso2": "BY", "iso3": "BLR", "name_en": "Belarus", "name_fr": "Biélorussie", "capital": "Minsk", "continent": "Europe", "currency": "BYN", "dial_code": "+375", "flag": "🇧🇾", "tld": ".by"},
    {"iso2": "BZ", "iso3": "BLZ", "name_en": "Belize", "name_fr": "Belize", "capital": "Belmopan", "continent": "Americas", "currency": "BZD", "dial_code": "+501", "flag": "🇧🇿", "tld": ".bz"},
    {"iso2": "CA", "iso3": "CAN", "name_en": "Canada", "name_fr": "Canada", "capital": "Ottawa", "continent": "Americas", "currency": "CAD", "dial_code": "+1", "flag": "🇨🇦", "tld": ".ca"},
    {"iso2": "CD", "iso3": "COD", "name_en": "DR Congo", "name_fr": "République démocratique du Congo", "capital": "Kinshasa", "continent": "Africa", "currency": "CDF", "dial_code": "+243", "flag": "🇨🇩", "tld": ".cd"},
    {"iso2": "CF", "iso3": "CAF", "name_en": "Central African Republic", "name_fr": "République centrafricaine", "capital": "Bangui", "continent": "Africa", "currency": "XAF", "dial_code": "+236", "flag": "🇨🇫", "tld": ".cf"},
    {"iso2": "CG", "iso3": "COG", "name_en": "Republic of the Congo", "name_fr": "République du Congo", "capital": "Brazzaville", "continent": "Africa", "currency": "XAF", "dial_code": "+242", "flag": "🇨🇬", "tld": ".cg"},
    {"iso2": "CH", "iso3": "CHE", "name_en": "Switzerland", "name_fr": "Suisse", "capital": "Bern", "continent": "Europe", "currency": "CHF", "dial_code": "+41", "flag": "🇨🇭", "tld": ".ch"},
    {"iso2": "CI", "iso3": "CIV", "name_en": "Ivory Coast", "name_fr": "Côte d'Ivoire", "capital": "Yamoussoukro", "continent": "Africa", "currency": "XOF", "dial_code": "+225", "flag": "🇨🇮", "tld": ".ci"},
    {"iso2": "CL", "iso3": "CHL", "name_en": "Chile", "name_fr": "Chili", "capital": "Santiago", "continent": "Americas", "currency": "CLP", "dial_code": "+56", "flag": "🇨🇱", "tld": ".cl"},
    {"iso2": "CM", "iso3": "CMR", "name_en": "Cameroon", "name_fr": "Cameroun", "capital": "Yaoundé", "continent": "Africa", "currency": "XAF", "dial_code": "+237", "flag": "🇨🇲", "tld": ".cm"},
    {"iso2": "CN", "iso3": "CHN", "name_en": "China", "name_fr": "Chine", "capital": "Beijing", "continent": "Asia", "currency": "CNY", "dial_code": "+86", "flag": "🇨🇳", "tld": ".cn"},
    {"iso2": "CO", "iso3": "COL", "name_en": "Colombia", "name_fr": "Colombie", "capital": "Bogotá", "continent": "Americas", "currency": "COP", "dial_code": "+57", "flag": "🇨🇴", "tld": ".co"},
    {"iso2": "CR", "iso3": "CRI", "name_en": "Costa Rica", "name_fr": "Costa Rica", "capital": "San José", "continent": "Americas", "currency": "CRC", "dial_code": "+506", "flag": "🇨🇷", "tld": ".cr"},
    {"iso2": "CU", "iso3": "CUB", "name_en": "Cuba", "name_fr": "Cuba", "capital": "Havana", "continent": "Americas", "currency": "CUP", "dial_code": "+53", "flag": "🇨🇺", "tld": ".cu"},
    {"iso2": "CV", "iso3": "CPV", "name_en": "Cape Verde", "name_fr": "Cap-Vert", "capital": "Praia", "continent": "Africa", "currency": "CVE", "dial_code": "+238", "flag": "🇨🇻", "tld": ".cv"},
    {"iso2": "CY", "iso3": "CYP", "name_en": "Cyprus", "name_fr": "Chypre", "capital": "Nicosia", "continent": "Europe", "currency": "EUR", "dial_code": "+357", "flag": "🇨🇾", "tld": ".cy"},
    {"iso2": "CZ", "iso3": "CZE", "name_en": "Czech Republic", "name_fr": "République tchèque", "capital": "Prague", "continent": "Europe", "currency": "CZK", "dial_code": "+420", "flag": "🇨🇿", "tld": ".cz"},
    {"iso2": "DE", "iso3": "DEU", "name_en": "Germany", "name_fr": "Allemagne", "capital": "Berlin", "continent": "Europe", "currency": "EUR", "dial_code": "+49", "flag": "🇩🇪", "tld": ".de"},
    {"iso2": "DJ", "iso3": "DJI", "name_en": "Djibouti", "name_fr": "Djibouti", "capital": "Djibouti", "continent": "Africa", "currency": "DJF", "dial_code": "+253", "flag": "🇩🇯", "tld": ".dj"},
    {"iso2": "DK", "iso3": "DNK", "name_en": "Denmark", "name_fr": "Danemark", "capital": "Copenhagen", "continent": "Europe", "currency": "DKK", "dial_code": "+45", "flag": "🇩🇰", "tld": ".dk"},
    {"iso2": "DO", "iso3": "DOM", "name_en": "Dominican Republic", "name_fr": "République dominicaine", "capital": "Santo Domingo", "continent": "Americas", "currency": "DOP", "dial_code": "+1-809", "flag": "🇩🇴", "tld": ".do"},
    {"iso2": "DZ", "iso3": "DZA", "name_en": "Algeria", "name_fr": "Algérie", "capital": "Algiers", "continent": "Africa", "currency": "DZD", "dial_code": "+213", "flag": "🇩🇿", "tld": ".dz"},
    {"iso2": "EC", "iso3": "ECU", "name_en": "Ecuador", "name_fr": "Équateur", "capital": "Quito", "continent": "Americas", "currency": "USD", "dial_code": "+593", "flag": "🇪🇨", "tld": ".ec"},
    {"iso2": "EE", "iso3": "EST", "name_en": "Estonia", "name_fr": "Estonie", "capital": "Tallinn", "continent": "Europe", "currency": "EUR", "dial_code": "+372", "flag": "🇪🇪", "tld": ".ee"},
    {"iso2": "EG", "iso3": "EGY", "name_en": "Egypt", "name_fr": "Égypte", "capital": "Cairo", "continent": "Africa", "currency": "EGP", "dial_code": "+20", "flag": "🇪🇬", "tld": ".eg"},
    {"iso2": "ER", "iso3": "ERI", "name_en": "Eritrea", "name_fr": "Érythrée", "capital": "Asmara", "continent": "Africa", "currency": "ERN", "dial_code": "+291", "flag": "🇪🇷", "tld": ".er"},
    {"iso2": "ES", "iso3": "ESP", "name_en": "Spain", "name_fr": "Espagne", "capital": "Madrid", "continent": "Europe", "currency": "EUR", "dial_code": "+34", "flag": "🇪🇸", "tld": ".es"},
    {"iso2": "ET", "iso3": "ETH", "name_en": "Ethiopia", "name_fr": "Éthiopie", "capital": "Addis Ababa", "continent": "Africa", "currency": "ETB", "dial_code": "+251", "flag": "🇪🇹", "tld": ".et"},
    {"iso2": "FI", "iso3": "FIN", "name_en": "Finland", "name_fr": "Finlande", "capital": "Helsinki", "continent": "Europe", "currency": "EUR", "dial_code": "+358", "flag": "🇫🇮", "tld": ".fi"},
    {"iso2": "FJ", "iso3": "FJI", "name_en": "Fiji", "name_fr": "Fidji", "capital": "Suva", "continent": "Oceania", "currency": "FJD", "dial_code": "+679", "flag": "🇫🇯", "tld": ".fj"},
    {"iso2": "FR", "iso3": "FRA", "name_en": "France", "name_fr": "France", "capital": "Paris", "continent": "Europe", "currency": "EUR", "dial_code": "+33", "flag": "🇫🇷", "tld": ".fr"},
    {"iso2": "GA", "iso3": "GAB", "name_en": "Gabon", "name_fr": "Gabon", "capital": "Libreville", "continent": "Africa", "currency": "XAF", "dial_code": "+241", "flag": "🇬🇦", "tld": ".ga"},
    {"iso2": "GB", "iso3": "GBR", "name_en": "United Kingdom", "name_fr": "Royaume-Uni", "capital": "London", "continent": "Europe", "currency": "GBP", "dial_code": "+44", "flag": "🇬🇧", "tld": ".uk"},
    {"iso2": "GE", "iso3": "GEO", "name_en": "Georgia", "name_fr": "Géorgie", "capital": "Tbilisi", "continent": "Asia", "currency": "GEL", "dial_code": "+995", "flag": "🇬🇪", "tld": ".ge"},
    {"iso2": "GH", "iso3": "GHA", "name_en": "Ghana", "name_fr": "Ghana", "capital": "Accra", "continent": "Africa", "currency": "GHS", "dial_code": "+233", "flag": "🇬🇭", "tld": ".gh"},
    {"iso2": "GM", "iso3": "GMB", "name_en": "Gambia", "name_fr": "Gambie", "capital": "Banjul", "continent": "Africa", "currency": "GMD", "dial_code": "+220", "flag": "🇬🇲", "tld": ".gm"},
    {"iso2": "GN", "iso3": "GIN", "name_en": "Guinea", "name_fr": "Guinée", "capital": "Conakry", "continent": "Africa", "currency": "GNF", "dial_code": "+224", "flag": "🇬🇳", "tld": ".gn"},
    {"iso2": "GQ", "iso3": "GNQ", "name_en": "Equatorial Guinea", "name_fr": "Guinée équatoriale", "capital": "Malabo", "continent": "Africa", "currency": "XAF", "dial_code": "+240", "flag": "🇬🇶", "tld": ".gq"},
    {"iso2": "GR", "iso3": "GRC", "name_en": "Greece", "name_fr": "Grèce", "capital": "Athens", "continent": "Europe", "currency": "EUR", "dial_code": "+30", "flag": "🇬🇷", "tld": ".gr"},
    {"iso2": "GT", "iso3": "GTM", "name_en": "Guatemala", "name_fr": "Guatemala", "capital": "Guatemala City", "continent": "Americas", "currency": "GTQ", "dial_code": "+502", "flag": "🇬🇹", "tld": ".gt"},
    {"iso2": "GW", "iso3": "GNB", "name_en": "Guinea-Bissau", "name_fr": "Guinée-Bissau", "capital": "Bissau", "continent": "Africa", "currency": "XOF", "dial_code": "+245", "flag": "🇬🇼", "tld": ".gw"},
    {"iso2": "GY", "iso3": "GUY", "name_en": "Guyana", "name_fr": "Guyana", "capital": "Georgetown", "continent": "Americas", "currency": "GYD", "dial_code": "+592", "flag": "🇬🇾", "tld": ".gy"},
    {"iso2": "HN", "iso3": "HND", "name_en": "Honduras", "name_fr": "Honduras", "capital": "Tegucigalpa", "continent": "Americas", "currency": "HNL", "dial_code": "+504", "flag": "🇭🇳", "tld": ".hn"},
    {"iso2": "HR", "iso3": "HRV", "name_en": "Croatia", "name_fr": "Croatie", "capital": "Zagreb", "continent": "Europe", "currency": "EUR", "dial_code": "+385", "flag": "🇭🇷", "tld": ".hr"},
    {"iso2": "HT", "iso3": "HTI", "name_en": "Haiti", "name_fr": "Haïti", "capital": "Port-au-Prince", "continent": "Americas", "currency": "HTG", "dial_code": "+509", "flag": "🇭🇹", "tld": ".ht"},
    {"iso2": "HU", "iso3": "HUN", "name_en": "Hungary", "name_fr": "Hongrie", "capital": "Budapest", "continent": "Europe", "currency": "HUF", "dial_code": "+36", "flag": "🇭🇺", "tld": ".hu"},
    {"iso2": "ID", "iso3": "IDN", "name_en": "Indonesia", "name_fr": "Indonésie", "capital": "Jakarta", "continent": "Asia", "currency": "IDR", "dial_code": "+62", "flag": "🇮🇩", "tld": ".id"},
    {"iso2": "IE", "iso3": "IRL", "name_en": "Ireland", "name_fr": "Irlande", "capital": "Dublin", "continent": "Europe", "currency": "EUR", "dial_code": "+353", "flag": "🇮🇪", "tld": ".ie"},
    {"iso2": "IL", "iso3": "ISR", "name_en": "Israel", "name_fr": "Israël", "capital": "Jerusalem", "continent": "Asia", "currency": "ILS", "dial_code": "+972", "flag": "🇮🇱", "tld": ".il"},
    {"iso2": "IN", "iso3": "IND", "name_en": "India", "name_fr": "Inde", "capital": "New Delhi", "continent": "Asia", "currency": "INR", "dial_code": "+91", "flag": "🇮🇳", "tld": ".in"},
    {"iso2": "IQ", "iso3": "IRQ", "name_en": "Iraq", "name_fr": "Irak", "capital": "Baghdad", "continent": "Asia", "currency": "IQD", "dial_code": "+964", "flag": "🇮🇶", "tld": ".iq"},
    {"iso2": "IR", "iso3": "IRN", "name_en": "Iran", "name_fr": "Iran", "capital": "Tehran", "continent": "Asia", "currency": "IRR", "dial_code": "+98", "flag": "🇮🇷", "tld": ".ir"},
    {"iso2": "IS", "iso3": "ISL", "name_en": "Iceland", "name_fr": "Islande", "capital": "Reykjavik", "continent": "Europe", "currency": "ISK", "dial_code": "+354", "flag": "🇮🇸", "tld": ".is"},
    {"iso2": "IT", "iso3": "ITA", "name_en": "Italy", "name_fr": "Italie", "capital": "Rome", "continent": "Europe", "currency": "EUR", "dial_code": "+39", "flag": "🇮🇹", "tld": ".it"},
    {"iso2": "JM", "iso3": "JAM", "name_en": "Jamaica", "name_fr": "Jamaïque", "capital": "Kingston", "continent": "Americas", "currency": "JMD", "dial_code": "+1-876", "flag": "🇯🇲", "tld": ".jm"},
    {"iso2": "JO", "iso3": "JOR", "name_en": "Jordan", "name_fr": "Jordanie", "capital": "Amman", "continent": "Asia", "currency": "JOD", "dial_code": "+962", "flag": "🇯🇴", "tld": ".jo"},
    {"iso2": "JP", "iso3": "JPN", "name_en": "Japan", "name_fr": "Japon", "capital": "Tokyo", "continent": "Asia", "currency": "JPY", "dial_code": "+81", "flag": "🇯🇵", "tld": ".jp"},
    {"iso2": "KE", "iso3": "KEN", "name_en": "Kenya", "name_fr": "Kenya", "capital": "Nairobi", "continent": "Africa", "currency": "KES", "dial_code": "+254", "flag": "🇰🇪", "tld": ".ke"},
    {"iso2": "KG", "iso3": "KGZ", "name_en": "Kyrgyzstan", "name_fr": "Kirghizistan", "capital": "Bishkek", "continent": "Asia", "currency": "KGS", "dial_code": "+996", "flag": "🇰🇬", "tld": ".kg"},
    {"iso2": "KH", "iso3": "KHM", "name_en": "Cambodia", "name_fr": "Cambodge", "capital": "Phnom Penh", "continent": "Asia", "currency": "KHR", "dial_code": "+855", "flag": "🇰🇭", "tld": ".kh"},
    {"iso2": "KI", "iso3": "KIR", "name_en": "Kiribati", "name_fr": "Kiribati", "capital": "South Tarawa", "continent": "Oceania", "currency": "AUD", "dial_code": "+686", "flag": "🇰🇮", "tld": ".ki"},
    {"iso2": "KM", "iso3": "COM", "name_en": "Comoros", "name_fr": "Comores", "capital": "Moroni", "continent": "Africa", "currency": "KMF", "dial_code": "+269", "flag": "🇰🇲", "tld": ".km"},
    {"iso2": "KP", "iso3": "PRK", "name_en": "North Korea", "name_fr": "Corée du Nord", "capital": "Pyongyang", "continent": "Asia", "currency": "KPW", "dial_code": "+850", "flag": "🇰🇵", "tld": ".kp"},
    {"iso2": "KR", "iso3": "KOR", "name_en": "South Korea", "name_fr": "Corée du Sud", "capital": "Seoul", "continent": "Asia", "currency": "KRW", "dial_code": "+82", "flag": "🇰🇷", "tld": ".kr"},
    {"iso2": "KW", "iso3": "KWT", "name_en": "Kuwait", "name_fr": "Koweït", "capital": "Kuwait City", "continent": "Asia", "currency": "KWD", "dial_code": "+965", "flag": "🇰🇼", "tld": ".kw"},
    {"iso2": "KZ", "iso3": "KAZ", "name_en": "Kazakhstan", "name_fr": "Kazakhstan", "capital": "Astana", "continent": "Asia", "currency": "KZT", "dial_code": "+7", "flag": "🇰🇿", "tld": ".kz"},
    {"iso2": "LA", "iso3": "LAO", "name_en": "Laos", "name_fr": "Laos", "capital": "Vientiane", "continent": "Asia", "currency": "LAK", "dial_code": "+856", "flag": "🇱🇦", "tld": ".la"},
    {"iso2": "LB", "iso3": "LBN", "name_en": "Lebanon", "name_fr": "Liban", "capital": "Beirut", "continent": "Asia", "currency": "LBP", "dial_code": "+961", "flag": "🇱🇧", "tld": ".lb"},
    {"iso2": "LI", "iso3": "LIE", "name_en": "Liechtenstein", "name_fr": "Liechtenstein", "capital": "Vaduz", "continent": "Europe", "currency": "CHF", "dial_code": "+423", "flag": "🇱🇮", "tld": ".li"},
    {"iso2": "LK", "iso3": "LKA", "name_en": "Sri Lanka", "name_fr": "Sri Lanka", "capital": "Colombo", "continent": "Asia", "currency": "LKR", "dial_code": "+94", "flag": "🇱🇰", "tld": ".lk"},
    {"iso2": "LR", "iso3": "LBR", "name_en": "Liberia", "name_fr": "Libéria", "capital": "Monrovia", "continent": "Africa", "currency": "LRD", "dial_code": "+231", "flag": "🇱🇷", "tld": ".lr"},
    {"iso2": "LS", "iso3": "LSO", "name_en": "Lesotho", "name_fr": "Lesotho", "capital": "Maseru", "continent": "Africa", "currency": "LSL", "dial_code": "+266", "flag": "🇱🇸", "tld": ".ls"},
    {"iso2": "LT", "iso3": "LTU", "name_en": "Lithuania", "name_fr": "Lituanie", "capital": "Vilnius", "continent": "Europe", "currency": "EUR", "dial_code": "+370", "flag": "🇱🇹", "tld": ".lt"},
    {"iso2": "LU", "iso3": "LUX", "name_en": "Luxembourg", "name_fr": "Luxembourg", "capital": "Luxembourg", "continent": "Europe", "currency": "EUR", "dial_code": "+352", "flag": "🇱🇺", "tld": ".lu"},
    {"iso2": "LV", "iso3": "LVA", "name_en": "Latvia", "name_fr": "Lettonie", "capital": "Riga", "continent": "Europe", "currency": "EUR", "dial_code": "+371", "flag": "🇱🇻", "tld": ".lv"},
    {"iso2": "LY", "iso3": "LBY", "name_en": "Libya", "name_fr": "Libye", "capital": "Tripoli", "continent": "Africa", "currency": "LYD", "dial_code": "+218", "flag": "🇱🇾", "tld": ".ly"},
    {"iso2": "MA", "iso3": "MAR", "name_en": "Morocco", "name_fr": "Maroc", "capital": "Rabat", "continent": "Africa", "currency": "MAD", "dial_code": "+212", "flag": "🇲🇦", "tld": ".ma"},
    {"iso2": "MC", "iso3": "MCO", "name_en": "Monaco", "name_fr": "Monaco", "capital": "Monaco", "continent": "Europe", "currency": "EUR", "dial_code": "+377", "flag": "🇲🇨", "tld": ".mc"},
    {"iso2": "MD", "iso3": "MDA", "name_en": "Moldova", "name_fr": "Moldavie", "capital": "Chisinau", "continent": "Europe", "currency": "MDL", "dial_code": "+373", "flag": "🇲🇩", "tld": ".md"},
    {"iso2": "ME", "iso3": "MNE", "name_en": "Montenegro", "name_fr": "Monténégro", "capital": "Podgorica", "continent": "Europe", "currency": "EUR", "dial_code": "+382", "flag": "🇲🇪", "tld": ".me"},
    {"iso2": "MG", "iso3": "MDG", "name_en": "Madagascar", "name_fr": "Madagascar", "capital": "Antananarivo", "continent": "Africa", "currency": "MGA", "dial_code": "+261", "flag": "🇲🇬", "tld": ".mg"},
    {"iso2": "MK", "iso3": "MKD", "name_en": "North Macedonia", "name_fr": "Macédoine du Nord", "capital": "Skopje", "continent": "Europe", "currency": "MKD", "dial_code": "+389", "flag": "🇲🇰", "tld": ".mk"},
    {"iso2": "ML", "iso3": "MLI", "name_en": "Mali", "name_fr": "Mali", "capital": "Bamako", "continent": "Africa", "currency": "XOF", "dial_code": "+223", "flag": "🇲🇱", "tld": ".ml"},
    {"iso2": "MM", "iso3": "MMR", "name_en": "Myanmar", "name_fr": "Myanmar", "capital": "Naypyidaw", "continent": "Asia", "currency": "MMK", "dial_code": "+95", "flag": "🇲🇲", "tld": ".mm"},
    {"iso2": "MN", "iso3": "MNG", "name_en": "Mongolia", "name_fr": "Mongolie", "capital": "Ulaanbaatar", "continent": "Asia", "currency": "MNT", "dial_code": "+976", "flag": "🇲🇳", "tld": ".mn"},
    {"iso2": "MR", "iso3": "MRT", "name_en": "Mauritania", "name_fr": "Mauritanie", "capital": "Nouakchott", "continent": "Africa", "currency": "MRU", "dial_code": "+222", "flag": "🇲🇷", "tld": ".mr"},
    {"iso2": "MT", "iso3": "MLT", "name_en": "Malta", "name_fr": "Malte", "capital": "Valletta", "continent": "Europe", "currency": "EUR", "dial_code": "+356", "flag": "🇲🇹", "tld": ".mt"},
    {"iso2": "MU", "iso3": "MUS", "name_en": "Mauritius", "name_fr": "Maurice", "capital": "Port Louis", "continent": "Africa", "currency": "MUR", "dial_code": "+230", "flag": "🇲🇺", "tld": ".mu"},
    {"iso2": "MV", "iso3": "MDV", "name_en": "Maldives", "name_fr": "Maldives", "capital": "Malé", "continent": "Asia", "currency": "MVR", "dial_code": "+960", "flag": "🇲🇻", "tld": ".mv"},
    {"iso2": "MW", "iso3": "MWI", "name_en": "Malawi", "name_fr": "Malawi", "capital": "Lilongwe", "continent": "Africa", "currency": "MWK", "dial_code": "+265", "flag": "🇲🇼", "tld": ".mw"},
    {"iso2": "MX", "iso3": "MEX", "name_en": "Mexico", "name_fr": "Mexique", "capital": "Mexico City", "continent": "Americas", "currency": "MXN", "dial_code": "+52", "flag": "🇲🇽", "tld": ".mx"},
    {"iso2": "MY", "iso3": "MYS", "name_en": "Malaysia", "name_fr": "Malaisie", "capital": "Kuala Lumpur", "continent": "Asia", "currency": "MYR", "dial_code": "+60", "flag": "🇲🇾", "tld": ".my"},
    {"iso2": "MZ", "iso3": "MOZ", "name_en": "Mozambique", "name_fr": "Mozambique", "capital": "Maputo", "continent": "Africa", "currency": "MZN", "dial_code": "+258", "flag": "🇲🇿", "tld": ".mz"},
    {"iso2": "NA", "iso3": "NAM", "name_en": "Namibia", "name_fr": "Namibie", "capital": "Windhoek", "continent": "Africa", "currency": "NAD", "dial_code": "+264", "flag": "🇳🇦", "tld": ".na"},
    {"iso2": "NE", "iso3": "NER", "name_en": "Niger", "name_fr": "Niger", "capital": "Niamey", "continent": "Africa", "currency": "XOF", "dial_code": "+227", "flag": "🇳🇪", "tld": ".ne"},
    {"iso2": "NG", "iso3": "NGA", "name_en": "Nigeria", "name_fr": "Nigéria", "capital": "Abuja", "continent": "Africa", "currency": "NGN", "dial_code": "+234", "flag": "🇳🇬", "tld": ".ng"},
    {"iso2": "NI", "iso3": "NIC", "name_en": "Nicaragua", "name_fr": "Nicaragua", "capital": "Managua", "continent": "Americas", "currency": "NIO", "dial_code": "+505", "flag": "🇳🇮", "tld": ".ni"},
    {"iso2": "NL", "iso3": "NLD", "name_en": "Netherlands", "name_fr": "Pays-Bas", "capital": "Amsterdam", "continent": "Europe", "currency": "EUR", "dial_code": "+31", "flag": "🇳🇱", "tld": ".nl"},
    {"iso2": "NO", "iso3": "NOR", "name_en": "Norway", "name_fr": "Norvège", "capital": "Oslo", "continent": "Europe", "currency": "NOK", "dial_code": "+47", "flag": "🇳🇴", "tld": ".no"},
    {"iso2": "NP", "iso3": "NPL", "name_en": "Nepal", "name_fr": "Népal", "capital": "Kathmandu", "continent": "Asia", "currency": "NPR", "dial_code": "+977", "flag": "🇳🇵", "tld": ".np"},
    {"iso2": "NR", "iso3": "NRU", "name_en": "Nauru", "name_fr": "Nauru", "capital": "Yaren", "continent": "Oceania", "currency": "AUD", "dial_code": "+674", "flag": "🇳🇷", "tld": ".nr"},
    {"iso2": "NZ", "iso3": "NZL", "name_en": "New Zealand", "name_fr": "Nouvelle-Zélande", "capital": "Wellington", "continent": "Oceania", "currency": "NZD", "dial_code": "+64", "flag": "🇳🇿", "tld": ".nz"},
    {"iso2": "OM", "iso3": "OMN", "name_en": "Oman", "name_fr": "Oman", "capital": "Muscat", "continent": "Asia", "currency": "OMR", "dial_code": "+968", "flag": "🇴🇲", "tld": ".om"},
    {"iso2": "PA", "iso3": "PAN", "name_en": "Panama", "name_fr": "Panama", "capital": "Panama City", "continent": "Americas", "currency": "PAB", "dial_code": "+507", "flag": "🇵🇦", "tld": ".pa"},
    {"iso2": "PE", "iso3": "PER", "name_en": "Peru", "name_fr": "Pérou", "capital": "Lima", "continent": "Americas", "currency": "PEN", "dial_code": "+51", "flag": "🇵🇪", "tld": ".pe"},
    {"iso2": "PG", "iso3": "PNG", "name_en": "Papua New Guinea", "name_fr": "Papouasie-Nouvelle-Guinée", "capital": "Port Moresby", "continent": "Oceania", "currency": "PGK", "dial_code": "+675", "flag": "🇵🇬", "tld": ".pg"},
    {"iso2": "PH", "iso3": "PHL", "name_en": "Philippines", "name_fr": "Philippines", "capital": "Manila", "continent": "Asia", "currency": "PHP", "dial_code": "+63", "flag": "🇵🇭", "tld": ".ph"},
    {"iso2": "PK", "iso3": "PAK", "name_en": "Pakistan", "name_fr": "Pakistan", "capital": "Islamabad", "continent": "Asia", "currency": "PKR", "dial_code": "+92", "flag": "🇵🇰", "tld": ".pk"},
    {"iso2": "PL", "iso3": "POL", "name_en": "Poland", "name_fr": "Pologne", "capital": "Warsaw", "continent": "Europe", "currency": "PLN", "dial_code": "+48", "flag": "🇵🇱", "tld": ".pl"},
    {"iso2": "PS", "iso3": "PSE", "name_en": "Palestine", "name_fr": "Palestine", "capital": "Ramallah", "continent": "Asia", "currency": "ILS", "dial_code": "+970", "flag": "🇵🇸", "tld": ".ps"},
    {"iso2": "PT", "iso3": "PRT", "name_en": "Portugal", "name_fr": "Portugal", "capital": "Lisbon", "continent": "Europe", "currency": "EUR", "dial_code": "+351", "flag": "🇵🇹", "tld": ".pt"},
    {"iso2": "PW", "iso3": "PLW", "name_en": "Palau", "name_fr": "Palaos", "capital": "Ngerulmud", "continent": "Oceania", "currency": "USD", "dial_code": "+680", "flag": "🇵🇼", "tld": ".pw"},
    {"iso2": "PY", "iso3": "PRY", "name_en": "Paraguay", "name_fr": "Paraguay", "capital": "Asuncion", "continent": "Americas", "currency": "PYG", "dial_code": "+595", "flag": "🇵🇾", "tld": ".py"},
    {"iso2": "QA", "iso3": "QAT", "name_en": "Qatar", "name_fr": "Qatar", "capital": "Doha", "continent": "Asia", "currency": "QAR", "dial_code": "+974", "flag": "🇶🇦", "tld": ".qa"},
    {"iso2": "RO", "iso3": "ROU", "name_en": "Romania", "name_fr": "Roumanie", "capital": "Bucharest", "continent": "Europe", "currency": "RON", "dial_code": "+40", "flag": "🇷🇴", "tld": ".ro"},
    {"iso2": "RS", "iso3": "SRB", "name_en": "Serbia", "name_fr": "Serbie", "capital": "Belgrade", "continent": "Europe", "currency": "RSD", "dial_code": "+381", "flag": "🇷🇸", "tld": ".rs"},
    {"iso2": "RU", "iso3": "RUS", "name_en": "Russia", "name_fr": "Russie", "capital": "Moscow", "continent": "Europe", "currency": "RUB", "dial_code": "+7", "flag": "🇷🇺", "tld": ".ru"},
    {"iso2": "RW", "iso3": "RWA", "name_en": "Rwanda", "name_fr": "Rwanda", "capital": "Kigali", "continent": "Africa", "currency": "RWF", "dial_code": "+250", "flag": "🇷🇼", "tld": ".rw"},
    {"iso2": "SA", "iso3": "SAU", "name_en": "Saudi Arabia", "name_fr": "Arabie saoudite", "capital": "Riyadh", "continent": "Asia", "currency": "SAR", "dial_code": "+966", "flag": "🇸🇦", "tld": ".sa"},
    {"iso2": "SB", "iso3": "SLB", "name_en": "Solomon Islands", "name_fr": "Îles Salomon", "capital": "Honiara", "continent": "Oceania", "currency": "SBD", "dial_code": "+677", "flag": "🇸🇧", "tld": ".sb"},
    {"iso2": "SC", "iso3": "SYC", "name_en": "Seychelles", "name_fr": "Seychelles", "capital": "Victoria", "continent": "Africa", "currency": "SCR", "dial_code": "+248", "flag": "🇸🇨", "tld": ".sc"},
    {"iso2": "SD", "iso3": "SDN", "name_en": "Sudan", "name_fr": "Soudan", "capital": "Khartoum", "continent": "Africa", "currency": "SDG", "dial_code": "+249", "flag": "🇸🇩", "tld": ".sd"},
    {"iso2": "SE", "iso3": "SWE", "name_en": "Sweden", "name_fr": "Suède", "capital": "Stockholm", "continent": "Europe", "currency": "SEK", "dial_code": "+46", "flag": "🇸🇪", "tld": ".se"},
    {"iso2": "SG", "iso3": "SGP", "name_en": "Singapore", "name_fr": "Singapour", "capital": "Singapore", "continent": "Asia", "currency": "SGD", "dial_code": "+65", "flag": "🇸🇬", "tld": ".sg"},
    {"iso2": "SI", "iso3": "SVN", "name_en": "Slovenia", "name_fr": "Slovénie", "capital": "Ljubljana", "continent": "Europe", "currency": "EUR", "dial_code": "+386", "flag": "🇸🇮", "tld": ".si"},
    {"iso2": "SK", "iso3": "SVK", "name_en": "Slovakia", "name_fr": "Slovaquie", "capital": "Bratislava", "continent": "Europe", "currency": "EUR", "dial_code": "+421", "flag": "🇸🇰", "tld": ".sk"},
    {"iso2": "SL", "iso3": "SLE", "name_en": "Sierra Leone", "name_fr": "Sierra Leone", "capital": "Freetown", "continent": "Africa", "currency": "SLL", "dial_code": "+232", "flag": "🇸🇱", "tld": ".sl"},
    {"iso2": "SM", "iso3": "SMR", "name_en": "San Marino", "name_fr": "Saint-Marin", "capital": "San Marino", "continent": "Europe", "currency": "EUR", "dial_code": "+378", "flag": "🇸🇲", "tld": ".sm"},
    {"iso2": "SN", "iso3": "SEN", "name_en": "Senegal", "name_fr": "Sénégal", "capital": "Dakar", "continent": "Africa", "currency": "XOF", "dial_code": "+221", "flag": "🇸🇳", "tld": ".sn"},
    {"iso2": "SO", "iso3": "SOM", "name_en": "Somalia", "name_fr": "Somalie", "capital": "Mogadishu", "continent": "Africa", "currency": "SOS", "dial_code": "+252", "flag": "🇸🇴", "tld": ".so"},
    {"iso2": "SR", "iso3": "SUR", "name_en": "Suriname", "name_fr": "Suriname", "capital": "Paramaribo", "continent": "Americas", "currency": "SRD", "dial_code": "+597", "flag": "🇸🇷", "tld": ".sr"},
    {"iso2": "SS", "iso3": "SSD", "name_en": "South Sudan", "name_fr": "Soudan du Sud", "capital": "Juba", "continent": "Africa", "currency": "SSP", "dial_code": "+211", "flag": "🇸🇸", "tld": ".ss"},
    {"iso2": "ST", "iso3": "STP", "name_en": "Sao Tome and Principe", "name_fr": "Sao Tomé-et-Principe", "capital": "Sao Tome", "continent": "Africa", "currency": "STN", "dial_code": "+239", "flag": "🇸🇹", "tld": ".st"},
    {"iso2": "SV", "iso3": "SLV", "name_en": "El Salvador", "name_fr": "Salvador", "capital": "San Salvador", "continent": "Americas", "currency": "USD", "dial_code": "+503", "flag": "🇸🇻", "tld": ".sv"},
    {"iso2": "SY", "iso3": "SYR", "name_en": "Syria", "name_fr": "Syrie", "capital": "Damascus", "continent": "Asia", "currency": "SYP", "dial_code": "+963", "flag": "🇸🇾", "tld": ".sy"},
    {"iso2": "SZ", "iso3": "SWZ", "name_en": "Eswatini", "name_fr": "Eswatini", "capital": "Mbabane", "continent": "Africa", "currency": "SZL", "dial_code": "+268", "flag": "🇸🇿", "tld": ".sz"},
    {"iso2": "TD", "iso3": "TCD", "name_en": "Chad", "name_fr": "Tchad", "capital": "N'Djamena", "continent": "Africa", "currency": "XAF", "dial_code": "+235", "flag": "🇹🇩", "tld": ".td"},
    {"iso2": "TG", "iso3": "TGO", "name_en": "Togo", "name_fr": "Togo", "capital": "Lomé", "continent": "Africa", "currency": "XOF", "dial_code": "+228", "flag": "🇹🇬", "tld": ".tg"},
    {"iso2": "TH", "iso3": "THA", "name_en": "Thailand", "name_fr": "Thaïlande", "capital": "Bangkok", "continent": "Asia", "currency": "THB", "dial_code": "+66", "flag": "🇹🇭", "tld": ".th"},
    {"iso2": "TJ", "iso3": "TJK", "name_en": "Tajikistan", "name_fr": "Tadjikistan", "capital": "Dushanbe", "continent": "Asia", "currency": "TJS", "dial_code": "+992", "flag": "🇹🇯", "tld": ".tj"},
    {"iso2": "TL", "iso3": "TLS", "name_en": "Timor-Leste", "name_fr": "Timor oriental", "capital": "Dili", "continent": "Asia", "currency": "USD", "dial_code": "+670", "flag": "🇹🇱", "tld": ".tl"},
    {"iso2": "TM", "iso3": "TKM", "name_en": "Turkmenistan", "name_fr": "Turkménistan", "capital": "Ashgabat", "continent": "Asia", "currency": "TMT", "dial_code": "+993", "flag": "🇹🇲", "tld": ".tm"},
    {"iso2": "TN", "iso3": "TUN", "name_en": "Tunisia", "name_fr": "Tunisie", "capital": "Tunis", "continent": "Africa", "currency": "TND", "dial_code": "+216", "flag": "🇹🇳", "tld": ".tn"},
    {"iso2": "TO", "iso3": "TON", "name_en": "Tonga", "name_fr": "Tonga", "capital": "Nuku'alofa", "continent": "Oceania", "currency": "TOP", "dial_code": "+676", "flag": "🇹🇴", "tld": ".to"},
    {"iso2": "TR", "iso3": "TUR", "name_en": "Turkey", "name_fr": "Turquie", "capital": "Ankara", "continent": "Asia", "currency": "TRY", "dial_code": "+90", "flag": "🇹🇷", "tld": ".tr"},
    {"iso2": "TT", "iso3": "TTO", "name_en": "Trinidad and Tobago", "name_fr": "Trinité-et-Tobago", "capital": "Port of Spain", "continent": "Americas", "currency": "TTD", "dial_code": "+1-868", "flag": "🇹🇹", "tld": ".tt"},
    {"iso2": "TV", "iso3": "TUV", "name_en": "Tuvalu", "name_fr": "Tuvalu", "capital": "Funafuti", "continent": "Oceania", "currency": "AUD", "dial_code": "+688", "flag": "🇹🇻", "tld": ".tv"},
    {"iso2": "TZ", "iso3": "TZA", "name_en": "Tanzania", "name_fr": "Tanzanie", "capital": "Dodoma", "continent": "Africa", "currency": "TZS", "dial_code": "+255", "flag": "🇹🇿", "tld": ".tz"},
    {"iso2": "UA", "iso3": "UKR", "name_en": "Ukraine", "name_fr": "Ukraine", "capital": "Kyiv", "continent": "Europe", "currency": "UAH", "dial_code": "+380", "flag": "🇺🇦", "tld": ".ua"},
    {"iso2": "UG", "iso3": "UGA", "name_en": "Uganda", "name_fr": "Ouganda", "capital": "Kampala", "continent": "Africa", "currency": "UGX", "dial_code": "+256", "flag": "🇺🇬", "tld": ".ug"},
    {"iso2": "US", "iso3": "USA", "name_en": "United States", "name_fr": "États-Unis", "capital": "Washington D.C.", "continent": "Americas", "currency": "USD", "dial_code": "+1", "flag": "🇺🇸", "tld": ".us"},
    {"iso2": "UY", "iso3": "URY", "name_en": "Uruguay", "name_fr": "Uruguay", "capital": "Montevideo", "continent": "Americas", "currency": "UYU", "dial_code": "+598", "flag": "🇺🇾", "tld": ".uy"},
    {"iso2": "UZ", "iso3": "UZB", "name_en": "Uzbekistan", "name_fr": "Ouzbékistan", "capital": "Tashkent", "continent": "Asia", "currency": "UZS", "dial_code": "+998", "flag": "🇺🇿", "tld": ".uz"},
    {"iso2": "VA", "iso3": "VAT", "name_en": "Vatican City", "name_fr": "Cité du Vatican", "capital": "Vatican City", "continent": "Europe", "currency": "EUR", "dial_code": "+379", "flag": "🇻🇦", "tld": ".va"},
    {"iso2": "VC", "iso3": "VCT", "name_en": "Saint Vincent and the Grenadines", "name_fr": "Saint-Vincent-et-les-Grenadines", "capital": "Kingstown", "continent": "Americas", "currency": "XCD", "dial_code": "+1-784", "flag": "🇻🇨", "tld": ".vc"},
    {"iso2": "VE", "iso3": "VEN", "name_en": "Venezuela", "name_fr": "Venezuela", "capital": "Caracas", "continent": "Americas", "currency": "VES", "dial_code": "+58", "flag": "🇻🇪", "tld": ".ve"},
    {"iso2": "VN", "iso3": "VNM", "name_en": "Vietnam", "name_fr": "Viêt Nam", "capital": "Hanoi", "continent": "Asia", "currency": "VND", "dial_code": "+84", "flag": "🇻🇳", "tld": ".vn"},
    {"iso2": "VU", "iso3": "VUT", "name_en": "Vanuatu", "name_fr": "Vanuatu", "capital": "Port Vila", "continent": "Oceania", "currency": "VUV", "dial_code": "+678", "flag": "🇻🇺", "tld": ".vu"},
    {"iso2": "WS", "iso3": "WSM", "name_en": "Samoa", "name_fr": "Samoa", "capital": "Apia", "continent": "Oceania", "currency": "WST", "dial_code": "+685", "flag": "🇼🇸", "tld": ".ws"},
    {"iso2": "YE", "iso3": "YEM", "name_en": "Yemen", "name_fr": "Yémen", "capital": "Sanaa", "continent": "Asia", "currency": "YER", "dial_code": "+967", "flag": "🇾🇪", "tld": ".ye"},
    {"iso2": "ZA", "iso3": "ZAF", "name_en": "South Africa", "name_fr": "Afrique du Sud", "capital": "Pretoria", "continent": "Africa", "currency": "ZAR", "dial_code": "+27", "flag": "🇿🇦", "tld": ".za"},
    {"iso2": "ZM", "iso3": "ZMB", "name_en": "Zambia", "name_fr": "Zambie", "capital": "Lusaka", "continent": "Africa", "currency": "ZMW", "dial_code": "+260", "flag": "🇿🇲", "tld": ".zm"},
    {"iso2": "ZW", "iso3": "ZWE", "name_en": "Zimbabwe", "name_fr": "Zimbabwe", "capital": "Harare", "continent": "Africa", "currency": "ZWL", "dial_code": "+263", "flag": "🇿🇼", "tld": ".zw"},
]

# Build lookup indices
_by_iso2 = {c["iso2"].upper(): c for c in COUNTRIES}
_by_iso3 = {c["iso3"].upper(): c for c in COUNTRIES}

PAID_PATHS = {"/code", "/search"}


def _make_402(host: str, endpoint: str = "/code/{code}") -> JSONResponse:
    return JSONResponse(
        status_code=402,
        content={"x402Version": 1, "error": "Payment required", "accepts": [{
            "scheme": "exact", "network": NETWORK, "maxAmountRequired": PRICE_ATOMIC,
            "resource": f"https://{host}/code/FR",
            "description": "Country data lookup by ISO code or name",
            "mimeType": "application/json", "payTo": PAY_TO, "maxTimeoutSeconds": 300,
            "asset": ASSET_ADDRESS, "extra": {"name": "USDC", "version": "2"},
        }]},
        headers={"Access-Control-Allow-Origin": "*", "Cache-Control": "no-store",
                 "Access-Control-Expose-Headers": "X-PAYMENT-RESPONSE"},
    )


@app.middleware("http")
async def x402_middleware(request: Request, call_next):
    path = request.url.path
    is_paid = (path.startswith("/code/") or path == "/search") and request.method == "GET"
    if is_paid:
        if not (request.headers.get("X-PAYMENT") or request.headers.get("x-payment")):
            return _make_402(request.headers.get("host", "x402-country.suretat.com"))
    return await call_next(request)


@app.get("/")
def root():
    return {"service": "x402 Country", "price": f"{int(PRICE_ATOMIC)/1_000_000} USDC/appel",
            "count": len(COUNTRIES), "docs": "/docs"}


@app.get("/code/{code}")
def get_by_code(code: str, request: Request):
    stats["total_paid"] += 1
    stats["revenue_usdc"] += int(PRICE_ATOMIC) / 1_000_000

    code_upper = code.upper()
    country = _by_iso2.get(code_upper) or _by_iso3.get(code_upper)

    if not country:
        return JSONResponse(status_code=404, content={"error": f"Country not found: {code}"})
    return country


@app.get("/search")
def search(q: str = Query(..., description="Country name (EN or FR)"), request: Request = None):
    stats["total_paid"] += 1
    stats["revenue_usdc"] += int(PRICE_ATOMIC) / 1_000_000

    q_lower = q.lower().strip()
    results = []
    for c in COUNTRIES:
        if (q_lower in c["name_en"].lower() or q_lower in c["name_fr"].lower()
                or q_lower in c["iso2"].lower() or q_lower in c["iso3"].lower()
                or q_lower in c["capital"].lower()):
            results.append(c)

    return {"query": q, "count": len(results), "results": results}


@app.get("/.well-known/x402.json")
async def x402_well_known(request: Request):
    host = request.headers.get("host", "x402-country.suretat.com")
    return {"x402Version": 1, "accepts": [{"scheme": "exact", "network": NETWORK,
        "maxAmountRequired": PRICE_ATOMIC, "resource": f"https://{host}/code/FR",
        "description": "Country data lookup by ISO code or name",
        "mimeType": "application/json", "payTo": PAY_TO, "maxTimeoutSeconds": 300,
        "asset": ASSET_ADDRESS, "extra": {"name": "USDC", "version": "2"}}]}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/stats")
def get_stats():
    return {**stats, "uptime_seconds": int(time.time() - stats["start_time"])}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=3111, proxy_headers=True, forwarded_allow_ips="*")
