from storygraph_api.request.books_request import BooksScraper
from storygraph_api.exception_handler import parsing_exception
from bs4 import BeautifulSoup
import re

class BooksParser:
    @staticmethod
    @parsing_exception
    def book_page(book_id, transport=None):
        content = BooksScraper.main(book_id, transport)
        soup = BeautifulSoup(content, 'html.parser')
        title_section = soup.find('div', class_='book-title-author-and-series')
        if title_section is None:
            raise ValueError('book title section not found')
        h3_tag = title_section.find('h3')
        title = h3_tag.get_text(' ', strip=True)
        authors = []
        for a in title_section.find_all('a'):
            if a["href"].startswith("/authors"):
                authors.append(a.get_text(' ', strip=True))
        p_tag = soup.find('p',class_="text-sm font-light text-darkestGrey dark:text-grey mt-1")
        metadata = p_tag.get_text(' ', strip=True) if p_tag else ''
        pages_match = re.search(r'(\d[\d,]*)\s+pages', metadata)
        first_pub_match = re.search(r'first pub\s+(\d{4})', metadata, re.IGNORECASE)
        pages = pages_match.group(1) if pages_match else None
        first_pub = first_pub_match.group(1) if first_pub_match else None
        tags = []
        tag_section = soup.find('div', class_="book-page-tag-section")
        if tag_section:
            tags = [tag.get_text(' ', strip=True) for tag in tag_section.find_all('span')]
        description_heading = soup.find(
            lambda tag: tag.name in ('h3', 'h4')
            and tag.get_text(' ', strip=True).lower() == 'description'
        )
        description_tag = description_heading.find_next(class_='trix-content') if description_heading else None
        description = description_tag.get_text('\n', strip=True) if description_tag else None
        review_content = BooksScraper.community_reviews(book_id, transport)
        rev_soup = BeautifulSoup(review_content,'html.parser')
        avg_rating_tag = rev_soup.find('span',class_="average-star-rating")
        avg_rating = avg_rating_tag.get_text(' ', strip=True) if avg_rating_tag else None
        warnings = BooksParser.content_warnings(book_id, transport)
        data = {
                'title':title,
                'authors': authors,
                'pages': pages,
                'first_pub': first_pub,
                'tags': tags,
                'average_rating': avg_rating,
                'description':description,
                'warnings': warnings
                }
        return data

    @staticmethod
    @parsing_exception
    def content_warnings(book_id, transport=None):
        warnings_content = BooksScraper.content_warnings(book_id, transport)
        warnings_soup = BeautifulSoup(warnings_content,'html.parser')
        user_warnings_pane = warnings_soup.find_all('div',class_='standard-pane')[1]
        warnings_graphic = []
        warnings_moderate = []
        warnings_minor = []
        warnings_list = warnings_graphic
        tag_re = re.compile(r'^(.*) \((\d+)\)$')
        for tag in user_warnings_pane.children:
            if tag == '\n':
                continue
            if tag.name == 'p':
                if tag.text == 'Graphic':
                    warnings_list = warnings_graphic
                elif tag.text == 'Moderate':
                    warnings_list = warnings_moderate
                elif tag.text == 'Minor':
                    warnings_list = warnings_minor
            elif tag.name == 'div':
                match = tag_re.match(tag.text)
                warnings_list.append(match[1])
        warnings = {
                'graphic': warnings_graphic,
                'moderate': warnings_moderate,
                'minor': warnings_minor
                }
        return warnings

    @staticmethod
    @parsing_exception
    def reading_progress(book_id, transport):
        soup = BeautifulSoup(BooksScraper.main(book_id, transport), 'html.parser')
        status_tag = soup.select_one('button.read-status-label')
        status = status_tag.get_text(' ', strip=True) if status_tag else None
        pages_tag = soup.select_one('input.read-status-last-reached-pages')
        percent_tag = soup.select_one('input.read-status-last-reached-percent')
        total_tag = soup.select_one('input.read-status-book-num-of-pages')
        pages = int(pages_tag.get('value', 0)) if pages_tag else None
        percent = int(percent_tag.get('value', 0)) if percent_tag else None
        total_pages = int(total_tag.get('value', 0)) if total_tag else None
        if status == 'read' and percent is None:
            percent = 100
        return {
            'status': status,
            'progress_pages': pages,
            'progress_percent': percent,
            'total_pages': total_pages,
        }

    @staticmethod
    @parsing_exception
    def journal_entries(book_id, transport):
        from storygraph_api.parse.user_parser import UserParser
        return UserParser.journal_entries(
            BooksScraper.journal(book_id, transport), book_id=book_id
        )

    @staticmethod
    @parsing_exception
    def read_dates(book_id, transport):
        from datetime import datetime

        entries = BooksParser.journal_entries(book_id, transport)
        started = None
        finished = None
        for entry in entries:
            if entry['book_id'] != book_id or not entry['date']:
                continue
            try:
                parsed = datetime.strptime(entry['date'], '%d %B %Y').date().isoformat()
            except ValueError:
                parsed = entry['date']
            if entry['status'] == 'Started reading' and started is None:
                started = parsed
            elif entry['status'] == 'Finished':
                finished = parsed
        return {'start_date': started, 'finish_date': finished}

    @staticmethod
    @parsing_exception
    def personalized_preview(book_id, user_id, transport):
        soup = BeautifulSoup(
            BooksScraper.personalized_preview(book_id, user_id, transport), 'html.parser'
        )
        template = soup.find('template')
        content = template.get_text('\n', strip=True) if template else soup.get_text('\n', strip=True)
        if not content:
            raise ValueError('personalized preview not available')
        return {'summary': content}

    @staticmethod
    @parsing_exception
    def search(query, transport=None):
        content = BooksScraper.search(query, transport)
        soup = BeautifulSoup(content, 'html.parser')
        search_results = []
        books = soup.select('li.book-list-item')
        if not books:
            books = soup.find_all('div', class_="book-title-author-and-series w-11/12")
        for book in books:
            book_link = book.find('a', href=re.compile(r'^/books/'))
            if not book_link:
                continue
            title_tag = book.select_one('.list-option-text') or book_link
            title = title_tag.get_text(' ', strip=True)
            author = None
            for a in book.find_all('a'):
                if a["href"].startswith('/author'):
                    author = a.text.strip()
                    break
            if author is None:
                accessible_name = book.select_one('.sr-only')
                label = accessible_name.get_text(' ', strip=True) if accessible_name else ''
                if ' by ' in label:
                    author = label.rsplit(' by ', 1)[1]
            book_id = book_link['href'].split('/')[-1]
            search_results.append({
                'title': title,
                'author': author,
                'book_id': book_id
            })
        return search_results
