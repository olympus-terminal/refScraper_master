#!/usr/bin/env python3
"""
RIS Citation Fetcher for Endnote Import
========================================
Fetches .ris formatted citations from PubMed and CrossRef APIs
Handles both PMIDs and DOIs

Usage:
    python ris_fetcher_20251022.py citations_input.txt

Input format (one per line):
    PMID:12345678
    DOI:10.1234/example

Output:
    Individual .ris files + combined bibliography.ris

Author: Generated for macroalgae manuscript
Date: 2025-10-22
"""

import sys
import time
import requests
from pathlib import Path
from typing import List, Tuple, Optional
import re

class RISFetcher:
    """Fetch RIS citations from PubMed and CrossRef"""

    def __init__(self, output_dir: str = "ris_citations"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) RIS Citation Fetcher/1.0',
            'Accept': 'application/x-research-info-systems'
        })

    def fetch_from_pubmed(self, pmid: str) -> Optional[str]:
        """
        Fetch RIS from PubMed using NCBI E-utilities
        PubMed supports RIS export via efetch
        """
        # Clean PMID
        pmid = pmid.strip().replace('PMID:', '').replace('pmid:', '')

        url = f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
        params = {
            'db': 'pubmed',
            'id': pmid,
            'rettype': 'medline',
            'retmode': 'text'
        }

        try:
            response = self.session.get(url, params=params, timeout=30)
            response.raise_for_status()

            # Convert MEDLINE to RIS format
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
            'TY': 'JOUR',  # Journal article
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

            # Parse MEDLINE fields
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
                # Continuation line
                ris_data[current_field] += ' ' + line.strip()

        # Build RIS format
        ris_lines = []
        ris_lines.append(f"TY  - {ris_data['TY']}")
        ris_lines.append(f"ID  - {ris_data['ID']}")

        for author in ris_data['AU']:
            ris_lines.append(f"AU  - {author}")

        if ris_data['TI']:
            ris_lines.append(f"TI  - {ris_data['TI']}")
        if ris_data['JO']:
            ris_lines.append(f"JO  - {ris_data['JO']}")
            ris_lines.append(f"T2  - {ris_data['JO']}")  # Alternative journal tag
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

    def fetch_from_crossref(self, doi: str) -> Optional[str]:
        """
        Fetch RIS from CrossRef API
        CrossRef supports content negotiation for RIS format
        """
        # Clean DOI
        doi = doi.strip().replace('DOI:', '').replace('doi:', '').replace('https://doi.org/', '')

        url = f"https://api.crossref.org/works/{doi}/transform/application/x-research-info-systems"

        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            return response.text

        except Exception as e:
            print(f"[ERROR] Error fetching DOI {doi}: {e}")
            return None

    def fetch_citation(self, identifier: str) -> Tuple[str, Optional[str]]:
        """
        Fetch citation based on identifier type (PMID or DOI)
        Returns (identifier_type, ris_content)
        """
        identifier = identifier.strip()

        # Determine type
        if identifier.upper().startswith('PMID:') or identifier.isdigit():
            pmid = identifier.replace('PMID:', '').replace('pmid:', '').strip()
            print(f"[FETCHING] Fetching PMID: {pmid}")
            ris = self.fetch_from_pubmed(pmid)
            return f"PMID_{pmid}", ris

        elif identifier.upper().startswith('DOI:') or '/' in identifier:
            doi = identifier.replace('DOI:', '').replace('doi:', '').strip()
            print(f"[FETCHING] Fetching DOI: {doi}")
            ris = self.fetch_from_crossref(doi)

            # Clean filename
            safe_doi = doi.replace('/', '_').replace('.', '_')
            return f"DOI_{safe_doi}", ris

        else:
            print(f"⚠️  Unknown identifier format: {identifier}")
            return identifier, None

    def process_batch(self, input_file: str) -> None:
        """Process batch of citations from input file"""

        input_path = Path(input_file)
        if not input_path.exists():
            print(f"[ERROR] Input file not found: {input_file}")
            return

        # Read identifiers
        with open(input_path, 'r') as f:
            identifiers = [line.strip() for line in f if line.strip() and not line.startswith('#')]

        print(f"\n{'='*60}")
        print(f"RIS CITATION FETCHER")
        print(f"{'='*60}")
        print(f"Input file: {input_file}")
        print(f"Citations to fetch: {len(identifiers)}")
        print(f"Output directory: {self.output_dir}")
        print(f"{'='*60}\n")

        # Fetch each citation
        combined_ris = []
        success_count = 0
        failed = []

        for i, identifier in enumerate(identifiers, 1):
            print(f"\n[{i}/{len(identifiers)}] ", end='')

            filename, ris_content = self.fetch_citation(identifier)

            if ris_content:
                # Save individual file
                output_file = self.output_dir / f"{filename}.ris"
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write(ris_content)

                combined_ris.append(ris_content)
                success_count += 1
                print(f"[SUCCESS] Saved: {output_file.name}")
            else:
                failed.append(identifier)
                print(f"[FAILED] Failed: {identifier}")

            # Rate limiting (be nice to APIs)
            if i < len(identifiers):
                time.sleep(0.5)

        # Save combined file
        if combined_ris:
            combined_file = self.output_dir / "bibliography_combined.ris"
            with open(combined_file, 'w', encoding='utf-8') as f:
                f.write('\n'.join(combined_ris))

            print(f"\n{'='*60}")
            print(f"[COMBINED] Combined bibliography: {combined_file}")
            print(f"{'='*60}")

        # Summary
        print(f"\n{'='*60}")
        print(f"SUMMARY")
        print(f"{'='*60}")
        print(f"[SUCCESS] Successfully fetched: {success_count}/{len(identifiers)}")
        if failed:
            print(f"[FAILED] Failed: {len(failed)}")
            print(f"   {', '.join(failed)}")
        print(f"\n[INFO] Import {self.output_dir}/bibliography_combined.ris into Endnote")
        print(f"{'='*60}\n")

def main():
    """Main entry point"""

    if len(sys.argv) < 2:
        print("""
Usage: python ris_fetcher_20251022.py <input_file>

Input file format (one per line):
    PMID:12345678
    DOI:10.1234/example.doi
    8248152
    10.1096/fasebj.7.15.8248152

Examples:
    python ris_fetcher_20251022.py citations_to_fetch.txt
    python ris_fetcher_20251022.py needed_pmids.txt
        """)
        sys.exit(1)

    input_file = sys.argv[1]
    fetcher = RISFetcher()
    fetcher.process_batch(input_file)

if __name__ == "__main__":
    main()
