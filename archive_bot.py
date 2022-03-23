"""
1. Bot finds pages with [[category:Articles flagged to be archived]]
2. Bot checks for template {{Archive recommendation|date=MONTH DAY, YEAR}}
3. Bot moves page to [[category:Articles Archived]]
4. Bot changes template from Archive recommendation to
   {{Archived|date=CURRENT_MONTH CURRENT_DAY, CURRENT_YEAR}}
"""
import json
import re
from datetime import datetime, timedelta
import requests
import urllib3
import pywikibot
from dateutil import parser


urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

REV_PAGE = "Powerpedia:ARCHIVE_BOT"
PAGES_LIMIT = 20



def get_api_url() -> str:
    """
    Retrieves the API URL of the wiki

    :return: String of the path to the API URL of the wiki
    """

    site = pywikibot.Site()
    url = site.protocol() + "://" + site.hostname() + site.apipath()
    return url
def check_last_page() -> str:
    """
    Checks to see if REV_PAGE has any useful last page to start the script from
    If it does return that page as the last_page, and if not return an empty string.
    Need to query the wiki for page rev information.
    Using this: https://www.mediawiki.org/wiki/API:Revisions

    :param: none
    :return: page last modified. Stored at REV_PAGE on wiki.  returns empty string if
    no information is available at that page.
    """

    page = pywikibot.Page(pywikibot.Site(), title=REV_PAGE)

    #Check to make sure the revision page exists.  If it doesn't create a new empty page and return
    #an empty string.
    if not page.exists():
        print("Revision page \""+ REV_PAGE +"\" not found...  Adding")
        page.text = ""
        page.save()
        return ""

    if not page.get():
        print("No valid revision on this page found\n")
        return ""


    #Need to replace ' with " so json.loads() can properly change it from a string to a dict.
    page_text = page.get().replace('\'', '\"')
    page_contents = json.loads(page_text)

    if page_contents['title']:
        return page_contents['title']

    print("No valid revision page found\n")
    return ""


def update_last_page(current_page: str) -> None:
    """
    Sets the page text of REV_PAGE to the latest revision information from current_page

    :param: current_page title of page to set revision information of
    :return: none
    """
    rev = get_revisions(current_page)
    page = pywikibot.Page(pywikibot.Site(), title=REV_PAGE)
    page.text = rev
    page.save()


def get_params(continue_from="") -> {}:
    """
    Gets the parameters dictionary to make the GET request to the wiki

    :param continue_from: String of page title to continue from; defaults to beginning of wiki
    :return: a dictionary of the parameters
    """

    return {
     "action": "query",
    "cmtitle": "Category:Articles flagged to be archived",
    "list": "categorymembers",
    "format": "json",
    "cmcontinue": continue_from,
    "cmlimit": PAGES_LIMIT
    }

def get_revisions(page_title: str) -> list:
    """
    Gets the revision information from a page specifed by its page title.

    :param page_title: string of the page title to get the revisions of
    :return: list containing user, time, and title of last revision on
    this page.
    """

    session = requests.Session()
    params = {
        "action": "query",
        "prop": "revisions",
        "titles": page_title,
        "rvprop": "timestamp|user",
        "rvslots": "main",
        "formatversion": "2",
        "format": "json"
    }

    request = session.get(url=get_api_url(), params=params, verify=False)
    data = request.json()

    #Need to make sure key values 'query' and 'pages' are in the data dict.
    if not ('query' in data and 'pages' in data['query']):
        print("No valid page found...")
        return ""

    page = data['query']['pages'][0]

    #Checking for 'missing' or no 'revisions' if so that means nothing of value
    #is page and should just return ""
    if 'missing' in page or not 'revisions' in page:
        print("No revision information found for page " + page_title + "\n")
        return ""
    rev_info = page['revisions'][0]

    return {"user": rev_info['user'],
            "time": rev_info['timestamp'],
            "title": page_title}

def grab_template_info(template_name: str, template: str) -> str:
    """
    Gets The template name and template information
    """

    front_prune = re.sub(r"\{{2}\s*"+template_name+"\s*\|",
                        "",
                        template)

    return re.sub("\}{2}","", front_prune)


def grab_template_data(template_name: str, text: str):
    """
    Takes the template name then returns data of template
    """

    templates = re.findall(r"\{{2}.*\}{2}", text)
    results = []
    for template in templates:
        if re.search(r"\{{2}\s*"+template_name+"\s*\|", template):
            results.append(grab_template_info(template_name, template))
    return results


def parse_template(template_name: str, text: str) -> dict:
    """
    Looks for template then checks if template is correct for archive
    returns dict
    """

    templates = re.findall(r"\{{2}.*\}{2}", text)
    results = []
    for template in templates:
        if re.search(r"\{{2}\s*"+template_name+"\s*\|", template):
            results.append(template)
    return results


def parse_date(date_string):
    """
    Finds date of archive recomendation
    """

    date = date_string.strip('date=')
    prased_date = parser.parse(date)

    return prased_date


def old_page(page) -> bool:
    """
    Checks if archive recommendation is less than 30 days old
    if >30 days then returns true
    if <30 days then returns false
    """

    dates = grab_template_data("Archive recommendation", page.text)
    if not dates:
        return False

    for date in dates:
        date = parse_date(date)
        if date < (datetime.now() - timedelta(days=30)):
            return True
    return False

def move_namespace(page, namespace: str) -> None:
    """
    Takes page then changes namespace to "Archived"
    """

    try:
        print("Moving namespace...")
        pagetitle = page.title(with_ns=False)
        old_namesp = page.site.namespace(page.namespace())
        new_page_title = '{}:{}'.format(namespace, pagetitle)
        page.move(new_page_title,
                  reason="Move namespace from " + old_namesp + " to " + namespace)
    except ArticleExistsConflictError:
        print("Same page already exists in new namespace...  Cannot move page")

def update_template(page):
    """
    Changes template "Archive recommendation" to "Archived"
    and adds current date to template.
    """

    print("Updating page's template...")
    templates = parse_template("Archive recommendation", page.text)
    new_text = page.text

    for template in templates:
        template = template.replace('|', '\|')
        new_text = re.sub(template, r'{{Archived|date='+
                        "{0:%B} {0:%d}, {0:%Y}".format(datetime.now())+"}}",
                          new_text)
    page.text = new_text


def update_category(page, old_cat, new_cat):
    """
    Saves new category to page
    """
    print("Changing category...")
    page.text = page.text.replace(old_cat, new_cat)
    page.save()

def update_page(page_dict: dict) -> None:
    """
    Checks if page Archive recommendation is old
    if true, then bot starts process of archiving template
    """

    page = pywikibot.Page(pywikibot.Site(), title=page_dict['title'])
    if old_page(page):
        update_template(page)
        update_category(page,
                        'Articles flagged to be archived',
                        'Articles Archived')
        move_namespace(page, "Archive")
    else:
        print("Page "+ page_dict['title'] + " does not need to be archived...")


def modify_pages(url: str, last_title: str) -> None:
    """
    Retrieves a Page Generator with all old pages to be tagged

    :param url: String of the path to the API URL of the wiki
    :param last_title: String of the last title scanned
    :return: None
    """

    # Retrieving the JSON and extracting page titles
    session = requests.Session()
    request = session.get(url=url, params=get_params(last_title), verify=False)
    pages_json = request.json()

    if not 'query' in pages_json:
        print("************INVALID JSON OBJECT************\n" +
              json.dumps(pages_json, indent=5))
    if not 'categorymembers' in pages_json['query']:
        print("************NO MEMBER FOUND IN CATEGORY************\n" +
              json.dumps(pages_json['query'], indent=5))

    for page in pages_json['query']['categorymembers']:
        print("WORKING ON PAGE "+ str(page))
        update_page(page)

 #   update_last_page()

def main() -> None:
    """
    Driver. Iterates through the wiki and adds TEMPLATE where needed.
    """
    # Retrieving the wiki URL
    url = get_api_url()
    last_title = check_last_page()
    if last_title:
        print("last page found")
    else:
        print("No last page found")

    modify_pages(url, last_title)


    print("\nNo pages left to be tagged")


if __name__ == '__main__':
    main()
