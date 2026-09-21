import collections
import collections.abc

# Compatibility fix for older libraries with Python 3.13
if not hasattr(collections, "Callable"):
    collections.Callable = collections.abc.Callable

import sqlite3
import urllib.error
import ssl
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen
from bs4 import BeautifulSoup

import sqlite3
import urllib.error
import ssl
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen
from bs4 import BeautifulSoup

# Ignore SSL certificate errors
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

# Open database
conn = sqlite3.connect("spider.sqlite")
cur = conn.cursor()

# Create tables
cur.execute("""
CREATE TABLE IF NOT EXISTS Pages (
    id INTEGER PRIMARY KEY,
    url TEXT UNIQUE,
    html TEXT,
    error INTEGER,
    old_rank REAL,
    new_rank REAL
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS Links (
    from_id INTEGER,
    to_id INTEGER,
    UNIQUE(from_id, to_id)
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS Webs (
    url TEXT UNIQUE
)
""")

# Ask for starting URL
starturl = input("Enter web url or enter: ").strip()

if len(starturl) == 0:
    starturl = "http://python-data.dr-chuck.net"

# Add http:// if the user didn't provide a scheme
if not starturl.startswith("http://") and not starturl.startswith("https://"):
    starturl = "http://" + starturl

# Remove trailing slash
if starturl.endswith("/"):
    starturl = starturl[:-1]

# Determine website/domain
parsed = urlparse(starturl)
web = parsed.scheme + "://" + parsed.netloc

print("Starting URL:", starturl)
print("Website:", web)

# Add website
cur.execute(
    "INSERT OR IGNORE INTO Webs (url) VALUES (?)",
    (web,)
)

# Add starting page
cur.execute(
    """INSERT OR IGNORE INTO Pages
       (url, html, new_rank)
       VALUES (?, NULL, 1.0)""",
    (starturl,)
)

conn.commit()

# Get websites
cur.execute("SELECT url FROM Webs")
webs = [row[0] for row in cur]

print("Allowed websites:", webs)

# Ask number of pages
sval = input("How many pages: ").strip()

if len(sval) == 0:
    sval = "100"

many = int(sval)

# Crawl pages
while many > 0:

    cur.execute("""
        SELECT id, url
        FROM Pages
        WHERE html IS NULL AND error IS NULL
        ORDER BY RANDOM()
        LIMIT 1
    """)

    row = cur.fetchone()

    if row is None:
        print("No unretrieved HTML pages found")
        break

    fromid = row[0]
    url = row[1]

    print(fromid, url, end=" ")

    # Remove old links from this page
    cur.execute(
        "DELETE FROM Links WHERE from_id=?",
        (fromid,)
    )

    try:
        # Create browser-like request
        request = Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0"
            }
        )

        document = urlopen(
            request,
            context=ctx,
            timeout=20
        )

        status = document.getcode()
        content_type = document.info().get_content_type()

        if status != 200:
            print("HTTP error:", status)
            cur.execute(
                "UPDATE Pages SET error=? WHERE id=?",
                (status, fromid)
            )
            conn.commit()
            many -= 1
            continue

        if content_type != "text/html":
            print("Not HTML:", content_type)
            cur.execute(
                "UPDATE Pages SET error=? WHERE id=?",
                (-2, fromid)
            )
            conn.commit()
            many -= 1
            continue

        html = document.read()

        print("(" + str(len(html)) + ")", end=" ")

        # Parse HTML
        soup = BeautifulSoup(html, "html.parser")

    except urllib.error.URLError as e:
        print("URL error:", e)
        cur.execute(
            "UPDATE Pages SET error=? WHERE id=?",
            (-1, fromid)
        )
        conn.commit()
        many -= 1
        continue

    except Exception as e:
        print("Error:", e)
        cur.execute(
            "UPDATE Pages SET error=? WHERE id=?",
            (-1, fromid)
        )
        conn.commit()
        many -= 1
        continue

    # Save HTML
    cur.execute(
        "UPDATE Pages SET html=? WHERE id=?",
        (memoryview(html), fromid)
    )

    conn.commit()

    # Find links
    tags = soup.find_all("a")
    count = 0

    for tag in tags:

        href = tag.get("href")

        if href is None:
            continue

        href = href.strip()

        if len(href) == 0:
            continue

        # Convert relative URL to absolute URL
        href = urljoin(url, href)

        # Remove fragment
        href = href.split("#")[0]

        # Parse URL
        parsed_href = urlparse(href)

        # Only HTTP/HTTPS
        if parsed_href.scheme not in ("http", "https"):
            continue

        # Remove trailing slash
        if href.endswith("/"):
            href = href[:-1]

        # Skip images and other files
        lower_href = href.lower()

        if lower_href.endswith((
            ".jpg",
            ".jpeg",
            ".png",
            ".gif",
            ".pdf",
            ".zip",
            ".css",
            ".js",
            ".mp3",
            ".mp4"
        )):
            continue

        # Only follow links belonging to our website
        found = False

        for site in webs:
            if href.startswith(site):
                found = True
                break

        if not found:
            continue

        # Add page
        cur.execute(
            """INSERT OR IGNORE INTO Pages
               (url, html, new_rank)
               VALUES (?, NULL, 1.0)""",
            (href,)
        )

        # Get page ID
        cur.execute(
            "SELECT id FROM Pages WHERE url=?",
            (href,)
        )

        target = cur.fetchone()

        if target is None:
            continue

        toid = target[0]

        # Add link
        cur.execute(
            """INSERT OR IGNORE INTO Links
               (from_id, to_id)
               VALUES (?, ?)""",
            (fromid, toid)
        )

        count += 1

    conn.commit()

    print("links:", count)

    many -= 1

print("Crawling complete.")

cur.close()
conn.close()