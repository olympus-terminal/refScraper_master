#!/usr/bin/env python3
"""
Expanded RIS Citation Fetcher
==============================
Fetches .ris formatted citations from multiple sources:
- PubMed (PMID)
- CrossRef (DOI)
- arXiv (arXiv ID)
- bioRxiv/medRxiv (DOI)
- Dataset repositories (Zenodo, Figshare, NOAA, DataCite)
- NASA Technical Reports
- Web URLs (any URL - uses universal citation fetcher)

Usage:
    python ris_fetcher_expanded.py citations_input.txt

Input format (one per line):
    PMID:12345678
    DOI:10.1234/example
    ARXIV:2311.17179
    BIORXIV:10.1101/2023.01.01.123456
    ZENODO:10.5281/zenodo.1234567
    NASA:20150000001
    URL:https://example.com/article
    https://github.com/owner/repo

Output:
    Individual .ris files + combined bibliography.ris

Date: 2025-11-30
"""

import sys
import time
import requests
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Tuple, Optional
import re
import json

class RISFetcherExpanded:
    """Fetch RIS citations from multiple academic sources"""

    def __init__(self, output_dir: str = "ris_citations"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) RIS Citation Fetcher/2.0',
            'Accept': 'application/x-research-info-systems'
        })

    # =========================================================================
    # arXiv Support
    # =========================================================================
    def fetch_from_arxiv(self, arxiv_id: str) -> Optional[str]:
        """
        Fetch citation from arXiv API and convert to RIS
        arXiv API returns Atom XML format
        """
        # Clean arXiv ID (handle various formats)
        arxiv_id = arxiv_id.strip()
        arxiv_id = re.sub(r'^(arxiv:|arXiv:)', '', arxiv_id, flags=re.IGNORECASE)
        arxiv_id = arxiv_id.replace('https://arxiv.org/abs/', '')
        arxiv_id = arxiv_id.replace('https://arxiv.org/pdf/', '').replace('.pdf', '')

        url = f"http://export.arxiv.org/api/query?id_list={arxiv_id}"

        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()

            # Parse Atom XML
            root = ET.fromstring(response.content)
            ns = {'atom': 'http://www.w3.org/2005/Atom',
                  'arxiv': 'http://arxiv.org/schemas/atom'}

            entry = root.find('atom:entry', ns)
            if entry is None:
                print(f"[ERROR] No entry found for arXiv:{arxiv_id}")
                return None

            # Extract metadata
            title = entry.find('atom:title', ns)
            title = title.text.strip().replace('\n', ' ') if title is not None else ''

            summary = entry.find('atom:summary', ns)
            abstract = summary.text.strip().replace('\n', ' ') if summary is not None else ''

            published = entry.find('atom:published', ns)
            year = published.text[:4] if published is not None else ''

            # Get authors
            authors = []
            for author in entry.findall('atom:author', ns):
                name = author.find('atom:name', ns)
                if name is not None:
                    authors.append(name.text)

            # Get categories/subjects
            categories = []
            for cat in entry.findall('arxiv:primary_category', ns):
                term = cat.get('term')
                if term:
                    categories.append(term)

            # Get DOI if available
            doi = ''
            for link in entry.findall('atom:link', ns):
                if link.get('title') == 'doi':
                    doi = link.get('href', '').replace('http://dx.doi.org/', '')

            # Build RIS
            ris_lines = [
                "TY  - UNPB",  # Unpublished work / preprint
                f"ID  - arXiv_{arxiv_id.replace('/', '_').replace('.', '_')}",
            ]

            for author in authors:
                # Convert "First Last" to "Last, First"
                parts = author.rsplit(' ', 1)
                if len(parts) == 2:
                    ris_lines.append(f"AU  - {parts[1]}, {parts[0]}")
                else:
                    ris_lines.append(f"AU  - {author}")

            ris_lines.append(f"TI  - {title}")
            ris_lines.append(f"PY  - {year}")
            ris_lines.append(f"PB  - arXiv")
            ris_lines.append(f"T2  - arXiv preprint")

            if abstract:
                ris_lines.append(f"AB  - {abstract[:2000]}")  # Truncate long abstracts

            if doi:
                ris_lines.append(f"DO  - {doi}")

            ris_lines.append(f"UR  - https://arxiv.org/abs/{arxiv_id}")
            ris_lines.append(f"M1  - arXiv:{arxiv_id}")

            if categories:
                ris_lines.append(f"KW  - {'; '.join(categories)}")

            ris_lines.append("ER  - ")
            ris_lines.append("")

            return '\n'.join(ris_lines)

        except Exception as e:
            print(f"[ERROR] Error fetching arXiv:{arxiv_id}: {e}")
            return None

    # =========================================================================
    # bioRxiv/medRxiv Support
    # =========================================================================
    def fetch_from_biorxiv(self, doi: str) -> Optional[str]:
        """
        Fetch citation from bioRxiv/medRxiv API
        They provide a JSON API for metadata
        """
        # Clean DOI
        doi = doi.strip()
        doi = re.sub(r'^(biorxiv:|medrxiv:|doi:)', '', doi, flags=re.IGNORECASE)
        doi = doi.replace('https://doi.org/', '')

        # bioRxiv API endpoint
        url = f"https://api.biorxiv.org/details/biorxiv/{doi}"

        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            data = response.json()

            if data.get('messages') and data['messages'][0].get('status') == 'no posts found':
                # Try medRxiv
                url = f"https://api.biorxiv.org/details/medrxiv/{doi}"
                response = self.session.get(url, timeout=30)
                response.raise_for_status()
                data = response.json()

            if not data.get('collection') or len(data['collection']) == 0:
                print(f"[ERROR] No data found for bioRxiv/medRxiv DOI: {doi}")
                # Fall back to CrossRef
                return self.fetch_from_crossref(doi)

            # Get the latest version
            paper = data['collection'][-1]

            # Build RIS
            ris_lines = [
                "TY  - UNPB",  # Preprint
                f"ID  - biorxiv_{doi.replace('/', '_').replace('.', '_')}",
            ]

            # Parse authors
            authors = paper.get('authors', '').split('; ')
            for author in authors:
                if author.strip():
                    ris_lines.append(f"AU  - {author.strip()}")

            ris_lines.append(f"TI  - {paper.get('title', '')}")

            date = paper.get('date', '')
            if date:
                year = date.split('-')[0]
                ris_lines.append(f"PY  - {year}")
                ris_lines.append(f"DA  - {date}")

            server = paper.get('server', 'biorxiv')
            ris_lines.append(f"PB  - {server}")
            ris_lines.append(f"T2  - {server} preprint")

            if paper.get('abstract'):
                ris_lines.append(f"AB  - {paper['abstract'][:2000]}")

            ris_lines.append(f"DO  - {paper.get('doi', doi)}")
            ris_lines.append(f"UR  - https://doi.org/{paper.get('doi', doi)}")

            if paper.get('category'):
                ris_lines.append(f"KW  - {paper['category']}")

            ris_lines.append("ER  - ")
            ris_lines.append("")

            return '\n'.join(ris_lines)

        except Exception as e:
            print(f"[ERROR] Error fetching bioRxiv {doi}: {e}")
            # Fall back to CrossRef
            return self.fetch_from_crossref(doi)

    # =========================================================================
    # DataCite Support (Zenodo, Figshare, NOAA datasets, etc.)
    # =========================================================================
    def fetch_from_datacite(self, doi: str) -> Optional[str]:
        """
        Fetch citation from DataCite API
        Works for Zenodo, Figshare, NOAA, and other dataset repositories
        """
        # Clean DOI
        doi = doi.strip()
        doi = re.sub(r'^(zenodo:|figshare:|dataset:|doi:)', '', doi, flags=re.IGNORECASE)
        doi = doi.replace('https://doi.org/', '')

        url = f"https://api.datacite.org/dois/{doi}"

        try:
            response = self.session.get(url, timeout=30,
                                        headers={'Accept': 'application/json'})
            response.raise_for_status()
            data = response.json()

            attrs = data.get('data', {}).get('attributes', {})

            if not attrs:
                print(f"[ERROR] No data found in DataCite for DOI: {doi}")
                return None

            # Determine type
            resource_type = attrs.get('types', {}).get('resourceTypeGeneral', 'Dataset')
            ris_type = 'DATA'  # Dataset
            if resource_type == 'Software':
                ris_type = 'COMP'
            elif resource_type == 'Text':
                ris_type = 'RPRT'  # Report

            # Build RIS
            ris_lines = [
                f"TY  - {ris_type}",
                f"ID  - datacite_{doi.replace('/', '_').replace('.', '_')}",
            ]

            # Authors/Creators
            for creator in attrs.get('creators', []):
                name = creator.get('name', '')
                if name:
                    ris_lines.append(f"AU  - {name}")

            # Title
            titles = attrs.get('titles', [])
            if titles:
                ris_lines.append(f"TI  - {titles[0].get('title', '')}")

            # Year
            year = attrs.get('publicationYear')
            if year:
                ris_lines.append(f"PY  - {year}")

            # Publisher
            publisher = attrs.get('publisher')
            if publisher:
                ris_lines.append(f"PB  - {publisher}")

            # Description/Abstract
            descriptions = attrs.get('descriptions', [])
            for desc in descriptions:
                if desc.get('descriptionType') == 'Abstract':
                    ris_lines.append(f"AB  - {desc.get('description', '')[:2000]}")
                    break

            # DOI and URL
            ris_lines.append(f"DO  - {doi}")
            ris_lines.append(f"UR  - https://doi.org/{doi}")

            # Version
            version = attrs.get('version')
            if version:
                ris_lines.append(f"ET  - {version}")

            # Keywords/Subjects
            subjects = attrs.get('subjects', [])
            if subjects:
                keywords = [s.get('subject', '') for s in subjects if s.get('subject')]
                if keywords:
                    ris_lines.append(f"KW  - {'; '.join(keywords[:10])}")

            ris_lines.append("ER  - ")
            ris_lines.append("")

            return '\n'.join(ris_lines)

        except Exception as e:
            print(f"[ERROR] Error fetching DataCite {doi}: {e}")
            return None

    # =========================================================================
    # NASA Technical Reports Server (NTRS)
    # =========================================================================
    def fetch_from_nasa(self, identifier: str) -> Optional[str]:
        """
        Fetch citation from NASA Technical Reports Server
        Accepts NTRS ID or NASA report number
        """
        # Clean identifier
        identifier = identifier.strip()
        identifier = re.sub(r'^(nasa:|ntrs:)', '', identifier, flags=re.IGNORECASE)

        # NASA NTRS API
        url = f"https://ntrs.nasa.gov/api/citations/{identifier}"

        try:
            response = self.session.get(url, timeout=30,
                                        headers={'Accept': 'application/json'})
            response.raise_for_status()
            data = response.json()

            if not data:
                print(f"[ERROR] No data found for NASA:{identifier}")
                return None

            # Build RIS
            ris_lines = [
                "TY  - RPRT",  # Report
                f"ID  - NASA_{identifier}",
            ]

            # Authors
            for author in data.get('authorAffiliations', []):
                name = author.get('meta', {}).get('author', {}).get('name', '')
                if name:
                    ris_lines.append(f"AU  - {name}")

            # Title
            title = data.get('title', '')
            if title:
                ris_lines.append(f"TI  - {title}")

            # Year
            pub_date = data.get('publications', [{}])[0].get('publicationDate', '')
            if pub_date:
                year = pub_date[:4]
                ris_lines.append(f"PY  - {year}")
                ris_lines.append(f"DA  - {pub_date}")

            # Publisher
            ris_lines.append("PB  - NASA")

            # Report number
            report_numbers = data.get('reportNumbers', [])
            if report_numbers:
                ris_lines.append(f"M1  - {report_numbers[0]}")

            # Abstract
            abstract = data.get('abstract', '')
            if abstract:
                ris_lines.append(f"AB  - {abstract[:2000]}")

            # URL
            ris_lines.append(f"UR  - https://ntrs.nasa.gov/citations/{identifier}")

            # Keywords
            keywords = data.get('keywords', [])
            if keywords:
                ris_lines.append(f"KW  - {'; '.join(keywords[:10])}")

            ris_lines.append("ER  - ")
            ris_lines.append("")

            return '\n'.join(ris_lines)

        except Exception as e:
            print(f"[ERROR] Error fetching NASA:{identifier}: {e}")
            return None

    # =========================================================================
    # PubMed (existing)
    # =========================================================================
    def fetch_from_pubmed(self, pmid: str) -> Optional[str]:
        """Fetch RIS from PubMed using NCBI E-utilities"""
        pmid = pmid.strip().replace('PMID:', '').replace('pmid:', '')

        url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
        params = {
            'db': 'pubmed',
            'id': pmid,
            'rettype': 'medline',
            'retmode': 'text'
        }

        try:
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()
            medline = response.text
            ris = self._medline_to_ris(medline, pmid)
            return ris

        except Exception as e:
            print(f"[ERROR] Error fetching PMID {pmid}: {e}")
            return None

    def _medline_to_ris(self, medline: str, pmid: str) -> str:
        """Convert MEDLINE format to RIS"""
        lines = medline.split('\n')

        ris_data = {
            'TY': 'JOUR',
            'ID': pmid,
            'AU': [],
            'TI': '',
            'JO': '',
            'PY': '',
            'VL': '',
            'IS': '',
            'SP': '',
            'EP': '',
            'AB': '',
            'DO': '',
            'PM': pmid
        }

        current_field = None

        for line in lines:
            line = line.strip()
            if not line:
                continue

            if line.startswith('AU  - '):
                ris_data['AU'].append(line[6:])
            elif line.startswith('TI  - '):
                ris_data['TI'] = line[6:]
                current_field = 'TI'
            elif line.startswith('TA  - '):
                ris_data['JO'] = line[6:]
            elif line.startswith('DP  - '):
                year_match = re.search(r'\d{4}', line[6:])
                if year_match:
                    ris_data['PY'] = year_match.group(0)
            elif line.startswith('VI  - '):
                ris_data['VL'] = line[6:]
            elif line.startswith('IP  - '):
                ris_data['IS'] = line[6:]
            elif line.startswith('PG  - '):
                pages = line[6:]
                if '-' in pages:
                    sp, ep = pages.split('-', 1)
                    ris_data['SP'] = sp.strip()
                    ris_data['EP'] = ep.strip()
                else:
                    ris_data['SP'] = pages
            elif line.startswith('AB  - '):
                ris_data['AB'] = line[6:]
                current_field = 'AB'
            elif line.startswith('AID - ') and '[doi]' in line:
                doi = line[6:].replace('[doi]', '').strip()
                ris_data['DO'] = doi
            elif line.startswith('      ') and current_field:
                ris_data[current_field] += ' ' + line.strip()

        ris_lines = []
        ris_lines.append(f"TY  - {ris_data['TY']}")
        ris_lines.append(f"ID  - {ris_data['ID']}")

        for author in ris_data['AU']:
            ris_lines.append(f"AU  - {author}")

        if ris_data['TI']:
            ris_lines.append(f"TI  - {ris_data['TI']}")
        if ris_data['JO']:
            ris_lines.append(f"JO  - {ris_data['JO']}")
            ris_lines.append(f"T2  - {ris_data['JO']}")
        if ris_data['PY']:
            ris_lines.append(f"PY  - {ris_data['PY']}")
        if ris_data['VL']:
            ris_lines.append(f"VL  - {ris_data['VL']}")
        if ris_data['IS']:
            ris_lines.append(f"IS  - {ris_data['IS']}")
        if ris_data['SP']:
            ris_lines.append(f"SP  - {ris_data['SP']}")
        if ris_data['EP']:
            ris_lines.append(f"EP  - {ris_data['EP']}")
        if ris_data['AB']:
            ris_lines.append(f"AB  - {ris_data['AB']}")
        if ris_data['DO']:
            ris_lines.append(f"DO  - {ris_data['DO']}")

        ris_lines.append(f"UR  - https://pubmed.ncbi.nlm.nih.gov/{pmid}/")
        ris_lines.append("ER  - ")
        ris_lines.append("")

        return '\n'.join(ris_lines)

    # =========================================================================
    # CrossRef (existing)
    # =========================================================================
    def fetch_from_crossref(self, doi: str) -> Optional[str]:
        """Fetch RIS from CrossRef API"""
        doi = doi.strip().replace('DOI:', '').replace('doi:', '').replace('https://doi.org/', '')

        url = f"https://api.crossref.org/works/{doi}/transform/application/x-research-info-systems"

        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            return response.text

        except Exception as e:
            print(f"[ERROR] Error fetching DOI {doi} from CrossRef: {e}")
            return None

    # =========================================================================
    # Web URL Support (uses universal citation fetcher)
    # =========================================================================
    def fetch_from_url(self, url: str) -> Tuple[str, Optional[str]]:
        """
        Fetch RIS citation from any web URL.
        Uses the universal citation fetcher with platform-specific handlers.
        """
        try:
            from universal_citation_fetcher import UniversalCitationFetcher
            fetcher = UniversalCitationFetcher(output_dir=str(self.output_dir))
            return fetcher.fetch_citation(url)
        except ImportError:
            print(f"[ERROR] Universal citation fetcher not available")
            print(f"[INFO] Make sure universal_citation_fetcher.py is in the same directory")
            return self._generate_url_filename(url), None
        except Exception as e:
            print(f"[ERROR] Error fetching URL {url}: {e}")
            return self._generate_url_filename(url), None

    def _generate_url_filename(self, url: str) -> str:
        """Generate safe filename from URL"""
        from urllib.parse import urlparse
        parsed = urlparse(url)
        domain = parsed.netloc.replace('www.', '').replace('.', '_')
        path = parsed.path.strip('/').replace('/', '_')[:50]
        safe = f"WEB_{domain}_{path}".replace('-', '_')
        return ''.join(c if c.isalnum() or c == '_' else '_' for c in safe)

    # =========================================================================
    # Main fetch dispatcher
    # =========================================================================
    def fetch_citation(self, identifier: str) -> Tuple[str, Optional[str]]:
        """
        Fetch citation based on identifier type
        Returns (identifier_label, ris_content)

        Supported formats:
            PMID:12345678
            DOI:10.1234/example
            ARXIV:2311.17179
            BIORXIV:10.1101/2023.01.01.123456
            MEDRXIV:10.1101/2023.01.01.123456
            ZENODO:10.5281/zenodo.1234567
            DATACITE:10.xxxx/xxxxx
            NASA:20150000001
        """
        identifier = identifier.strip()
        id_upper = identifier.upper()

        # arXiv
        if id_upper.startswith('ARXIV:') or 'arxiv.org' in identifier.lower():
            arxiv_id = re.sub(r'^arxiv:', '', identifier, flags=re.IGNORECASE)
            arxiv_id = arxiv_id.replace('https://arxiv.org/abs/', '').replace('https://arxiv.org/pdf/', '').replace('.pdf', '')
            print(f"[FETCHING] Fetching arXiv: {arxiv_id}")
            ris = self.fetch_from_arxiv(arxiv_id)
            safe_id = arxiv_id.replace('/', '_').replace('.', '_')
            return f"arXiv_{safe_id}", ris

        # bioRxiv
        elif id_upper.startswith('BIORXIV:') or '10.1101/' in identifier:
            doi = re.sub(r'^biorxiv:', '', identifier, flags=re.IGNORECASE)
            print(f"[FETCHING] Fetching bioRxiv: {doi}")
            ris = self.fetch_from_biorxiv(doi)
            safe_doi = doi.replace('/', '_').replace('.', '_')
            return f"bioRxiv_{safe_doi}", ris

        # medRxiv
        elif id_upper.startswith('MEDRXIV:'):
            doi = re.sub(r'^medrxiv:', '', identifier, flags=re.IGNORECASE)
            print(f"[FETCHING] Fetching medRxiv: {doi}")
            ris = self.fetch_from_biorxiv(doi)
            safe_doi = doi.replace('/', '_').replace('.', '_')
            return f"medRxiv_{safe_doi}", ris

        # Zenodo
        elif id_upper.startswith('ZENODO:') or '10.5281/zenodo' in identifier.lower():
            doi = re.sub(r'^zenodo:', '', identifier, flags=re.IGNORECASE)
            print(f"[FETCHING] Fetching Zenodo: {doi}")
            ris = self.fetch_from_datacite(doi)
            safe_doi = doi.replace('/', '_').replace('.', '_')
            return f"Zenodo_{safe_doi}", ris

        # DataCite (generic)
        elif id_upper.startswith('DATACITE:'):
            doi = re.sub(r'^datacite:', '', identifier, flags=re.IGNORECASE)
            print(f"[FETCHING] Fetching DataCite: {doi}")
            ris = self.fetch_from_datacite(doi)
            safe_doi = doi.replace('/', '_').replace('.', '_')
            return f"DataCite_{safe_doi}", ris

        # NASA Technical Reports
        elif id_upper.startswith('NASA:') or id_upper.startswith('NTRS:'):
            nasa_id = re.sub(r'^(nasa:|ntrs:)', '', identifier, flags=re.IGNORECASE)
            print(f"[FETCHING] Fetching NASA: {nasa_id}")
            ris = self.fetch_from_nasa(nasa_id)
            return f"NASA_{nasa_id}", ris

        # NOAA (try DataCite first, then CrossRef)
        elif id_upper.startswith('NOAA:') or '10.7289/' in identifier:
            doi = re.sub(r'^noaa:', '', identifier, flags=re.IGNORECASE)
            print(f"[FETCHING] Fetching NOAA dataset: {doi}")
            ris = self.fetch_from_datacite(doi)
            if not ris:
                ris = self.fetch_from_crossref(doi)
            safe_doi = doi.replace('/', '_').replace('.', '_')
            return f"NOAA_{safe_doi}", ris

        # PubMed
        elif id_upper.startswith('PMID:') or identifier.isdigit():
            pmid = identifier.replace('PMID:', '').replace('pmid:', '').strip()
            print(f"[FETCHING] Fetching PMID: {pmid}")
            ris = self.fetch_from_pubmed(pmid)
            return f"PMID_{pmid}", ris

        # DOI (generic - try CrossRef first, then DataCite)
        elif id_upper.startswith('DOI:') or ('/' in identifier and not identifier.startswith('http')):
            doi = identifier.replace('DOI:', '').replace('doi:', '').strip()
            print(f"[FETCHING] Fetching DOI: {doi}")
            ris = self.fetch_from_crossref(doi)
            if not ris:
                print(f"[INFO] CrossRef failed, trying DataCite...")
                ris = self.fetch_from_datacite(doi)
            safe_doi = doi.replace('/', '_').replace('.', '_')
            return f"DOI_{safe_doi}", ris

        # Web URLs (generic - uses universal citation fetcher)
        elif identifier.startswith('http://') or identifier.startswith('https://') or id_upper.startswith('URL:'):
            url = identifier
            if id_upper.startswith('URL:'):
                url = identifier[4:].strip()
            print(f"[FETCHING] Fetching URL: {url[:60]}...")
            return self.fetch_from_url(url)

        else:
            print(f"[WARNING] Unknown identifier format: {identifier}")
            return identifier, None

    # =========================================================================
    # Batch processing
    # =========================================================================
    def process_batch(self, input_file: str) -> None:
        """Process batch of citations from input file"""

        input_path = Path(input_file)
        if not input_path.exists():
            print(f"[ERROR] Input file not found: {input_file}")
            return

        with open(input_path, 'r') as f:
            identifiers = [line.strip() for line in f if line.strip() and not line.startswith('#')]

        print(f"\n{'='*70}")
        print(f"EXPANDED RIS CITATION FETCHER")
        print(f"{'='*70}")
        print(f"Input file: {input_file}")
        print(f"Citations to fetch: {len(identifiers)}")
        print(f"Output directory: {self.output_dir}")
        print(f"Supported sources: PubMed, CrossRef, arXiv, bioRxiv, medRxiv,")
        print(f"                   Zenodo, DataCite, NOAA, NASA NTRS")
        print(f"{'='*70}\n")

        combined_ris = []
        success_count = 0
        failed = []

        for i, identifier in enumerate(identifiers, 1):
            print(f"\n[{i}/{len(identifiers)}] ", end='')

            filename, ris_content = self.fetch_citation(identifier)

            if ris_content:
                output_file = self.output_dir / f"{filename}.ris"
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write(ris_content)

                combined_ris.append(ris_content)
                success_count += 1
                print(f"[SUCCESS] Saved: {output_file.name}")
            else:
                failed.append(identifier)
                print(f"[FAILED] Failed: {identifier}")

            if i < len(identifiers):
                time.sleep(0.5)

        if combined_ris:
            combined_file = self.output_dir / "bibliography_combined.ris"
            with open(combined_file, 'w', encoding='utf-8') as f:
                f.write('\n'.join(combined_ris))

            print(f"\n{'='*70}")
            print(f"[COMBINED] Combined bibliography: {combined_file}")
            print(f"{'='*70}")

        print(f"\n{'='*70}")
        print(f"SUMMARY")
        print(f"{'='*70}")
        print(f"[SUCCESS] Successfully fetched: {success_count}/{len(identifiers)}")
        if failed:
            print(f"[FAILED] Failed: {len(failed)}")
            for f_id in failed:
                print(f"   - {f_id}")
        print(f"\n[INFO] Import {self.output_dir}/bibliography_combined.ris into Endnote")
        print(f"{'='*70}\n")

def main():
    """Main entry point"""

    if len(sys.argv) < 2:
        print("""
Expanded RIS Citation Fetcher
=============================

Usage: python ris_fetcher_expanded.py <input_file>

Input file format (one per line):
    PMID:12345678          - PubMed ID
    DOI:10.1234/example    - CrossRef DOI
    ARXIV:2311.17179       - arXiv preprint
    BIORXIV:10.1101/xxx    - bioRxiv preprint
    MEDRXIV:10.1101/xxx    - medRxiv preprint
    ZENODO:10.5281/xxx     - Zenodo dataset
    DATACITE:10.xxxx/xxx   - DataCite DOI
    NOAA:10.7289/xxx       - NOAA dataset
    NASA:20150000001       - NASA Technical Report

Examples:
    python ris_fetcher_expanded.py citations.txt
    python ris_fetcher_expanded.py preprints.txt
        """)
        sys.exit(1)

    input_file = sys.argv[1]
    fetcher = RISFetcherExpanded()
    fetcher.process_batch(input_file)

if __name__ == "__main__":
    main()
