import csv
from database import get_all_leads
from utils import logger

def export_leads_to_csv(filepath: str) -> bool:
    """
    Exports all leads from the SQLite database to a CSV file.
    Returns True if successful, False if there are no leads or an error occurs.
    """
    leads = get_all_leads()
    if not leads:
        logger.warning("No leads in database to export.")
        return False
        
    headers = [
        "id", "name", "niche", "city", "url", "instagram_url", "website_url",
        "source_domain", "source_type", "title", "snippet", "score",
        "score_reason", "recommended_demo", "suggested_message", "custom_angle",
        "status", "follow_up_date", "created_at", "updated_at"
    ]
    
    try:
        with open(filepath, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            for lead in leads:
                # Build row matching the header order precisely
                row = {header: lead.get(header) for header in headers}
                # Handle None values nicely by replacing them with empty strings
                for k, v in row.items():
                    if v is None:
                        row[k] = ""
                writer.writerow(row)
        logger.info(f"Successfully exported {len(leads)} leads to CSV at: {filepath}")
        return True
    except Exception as e:
        logger.error(f"Failed to write CSV file: {e}")
        return False
