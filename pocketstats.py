import datetime
from time import mktime
import json
import logging
import sys
import __main__ as main
import pocket
from pocket import Pocket
import click
from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy import desc
from sqlalchemy import create_engine
from sqlalchemy import func
from sqlalchemy import extract
from sqlalchemy.orm import sessionmaker
from sqlalchemy.engine.reflection import Inspector
from sqlalchemy.ext.declarative import declarative_base
Base = declarative_base()

try:
    import settings
except ImportError:
    print('Copy settings_example.py to settings.py and set the configuration to your own preferences')
    sys.exit(1)

# Debugging can be overridden in settings.py
try:
    DEBUG = settings.DEBUG
except AttributeError:
    DEBUG = False


def safe_unicode(obj, *args):
    """ return the unicode representation of obj """
    try:
        return unicode(obj, *args)
    except UnicodeDecodeError:
        # obj is byte string
        ascii_text = str(obj).encode('string_escape')
        return unicode(ascii_text)

def safe_str(obj):
    """ return the byte string representation of obj """
    try:
        return str(obj)
    except UnicodeEncodeError:
        # obj is unicode
        return unicode(obj).encode('unicode_escape')


def debug_print(string):
    if DEBUG:
        print string


def unix_to_string(timestamp):
    return datetime.datetime.fromtimestamp(int(timestamp)).strftime('%Y-%m-%d %H:%M:%S')


def unix_to_python(timestamp):
    """
    Convert unix timestamp to python datetime
    """
    # Not sure how correct this is to do here, but return 'null' if the timestamp from Pocket is 0
    if int(timestamp) == 0:
        return None
    else:
        return datetime.datetime.utcfromtimestamp(float(timestamp))


def datetime_to_string(timestamp):
    return timestamp.strftime('%Y-%m-%d %H:%M:%S')


def get_logger():
    """
    Create logging handler
    """
    ## Create logger
    logger = logging.getLogger('pocketstats')
    logger.setLevel(logging.DEBUG)
    # create file handler which logs even debug messages
    fh = logging.FileHandler('pocketstats.log')
    fh.setLevel(logging.DEBUG)
    # create formatter and add it to the handlers
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    fh.setFormatter(formatter)
    # add the handlers to the logger
    logger.addHandler(fh)
    return logger


class Article(Base):
    """
    An item in the Pocket archive; can also be an Image or Video
    """
    __tablename__ = 'article'

    id = Column(Integer, primary_key=True)
    sort_id = Column(Integer)
    item_id = Column(Integer)
    resolved_id = Column(Integer)
    given_url = Column(String)
    resolved_url = Column(String)
    given_title = Column(String)
    resolved_title = Column(String)

    # 0 or 1 - 1 If the item is favorited
    favorite = Column(Integer)

    # 0, 1, 2 - 1 if the item is archived - 2 if the item should be deleted
    status = Column(Integer)
    firstseen_status = Column(Integer)

    excerpt = Column(Text)

    # 0 or 1 - 1 if the item is an article
    is_article = Column(Integer)

    # 0, 1, or 2 - 1 if the item has images in it - 2 if the item is an image
    has_image = Column(Integer)

    # 0, 1, or 2 - 1 if the item has videos in it - 2 if the item is a video
    has_video = Column(Integer)

    # How many words are in the article
    word_count = Column(Integer)

    # JSON objects
    tags = Column(Text)
    authors = Column(Text)
    images = Column(Text)
    videos = Column(Text)

    # First import of this item
    firstseen_time = Column(DateTime)
    # time_updated at time of the first import
    firstseen_time_updated = Column(DateTime)
    #local_updated = Column(DateTime)

    time_updated = Column(DateTime)
    time_favorited = Column(DateTime)
    time_read = Column(DateTime)


class Report(Base):
    """
    Changes since the last report; e.g., how many added, read, deleted, favourited
    """
    __tablename__ = 'report'

    id = Column(Integer, primary_key=True)
    # Local DateTime of request
    time_updated = Column(DateTime)
    # DateTime stamp that Pocket reported for this request
    time_since = Column(DateTime)
    # Stats
    total_response = Column(Integer)
    nr_added = Column(Integer)
    nr_read = Column(Integer)
    nr_deleted = Column(Integer)
    nr_favourited = Column(Integer)
    # Has updates according to change in time_updated
    nr_updated = Column(Integer)
    # Response metadata
    status = Column(Integer)
    complete = Column(Integer)
    error = Column(Text)

    def pretty_print(self):
        """
        Return a pretty overview of the report, usable for printing as import result
        """
        data = [['update at', datetime_to_string(self.time_updated)], ['total in response', str(self.total_response)], ['updated', str(self.nr_updated)], ['added', str(self.nr_added)], ['read', str(self.nr_read)], ['favourited', str(self.nr_favourited)], ['deleted', str(self.nr_deleted)]]
        result = ''
        col_width = max(len(word) for row in data for word in row) + 2  # padding
        for row in data:
            result += "".join(word.ljust(col_width) for word in row) + "\n"
        return result


    def __str__(self):
        return u'Update at ' + datetime_to_string(self.time_updated) + '; total in response: ' + str(self.total_response) + ', nr_updated: ' + str(self.nr_updated) + ', nr_added: ' + str(self.nr_added) + ', nr_read: ' + str(self.nr_read) + ', nr_favourited: ' + str(self.nr_favourited) + ', nr_deleted: ' + str(self.nr_deleted)


    def __unicode__(self):
        return self.__str__()


    def __repr__(self):
        return self.__str__()


def get_pocket_instance():
    """
    Connect to Pocket API
    """
    consumer_key = settings.consumer_key
    access_token = settings.access_token

    pocket_instance = pocket.Pocket(consumer_key, access_token)
    return pocket_instance


def get_db_connection(get_engine=False):
    """
    Create a SQLAlchemy session
    """
    #engine = create_engine('sqlite:///:memory:', echo=True)
    # Relative path:
    engine = create_engine('sqlite:///pocketstats.db')
    Session = sessionmaker(bind=engine)
    if get_engine:
        return Session(),engine
    else:
        return Session()


def _create_tables():
    session, engine = get_db_connection(get_engine=True)

    inspector = Inspector.from_engine(engine)
    #for table_name in inspector.get_table_names():
    #    print table_name
    if (engine.dialect.has_table(engine.connect(), "Article") == False) or (engine.dialect.has_table(engine.connect(), "Report") == False):
        # TODO: If Article and Report don't exist yet, create:
        Base.metadata.create_all(engine)


def get_last_update():
    """
    Return the timestamp of the last update from Pocket.
    This will be used to filter the request of updates.
    """
    session = get_db_connection()
    try:
        time_since, report_id = session.query(Report.time_since, Report.id).order_by(desc(Report.time_since))[0]
        return mktime(time_since.timetuple())
    except IndexError:
        return None


def get_existing_item(item_id):
    """
    Returns the item with item_id if already in DB, otherwise None
    """
    session = get_db_connection()
    try:
        return session.query(Article).filter(Article.item_id == item_id)[0]
    except IndexError:
        return None


def get_count(q):
    """
    Fast count for column, avoiding a subquery
    """
    count_q = q.statement.with_only_columns([func.count()]).order_by(None)
    count = q.session.execute(count_q).scalar()
    return count


## Main program
@click.group()
def cli():
    """
    Pocket stats
    """
    pass


@cli.command()
def updatestats():
    """
    Get the changes since last time from the Pocket API
    """
    logger = get_logger()
    session = get_db_connection()

    last_time = get_last_update()
    debug_print(last_time)

    pocket_instance = get_pocket_instance()
    if last_time:
        items = pocket_instance.get(since=last_time, state='all', detailType='complete')
    else:
        if DEBUG:
            # When debugging, limit to 20 items
            items = pocket_instance.get(count=20, state='all', detailType='complete')
        else:
            items = pocket_instance.get(state='all', detailType='complete')
    debug_print('Number of items in reponse: ' + str(len(items[0]['list'])))
    logger.debug('Number of items in response: ' + str(len(items[0]['list'])))

    now = datetime.datetime.now()
    report = Report(time_updated=now)
    nr_added = 0
    nr_read = 0
    nr_deleted = 0
    nr_favourited = 0
    nr_updated = 0
    report.time_since = unix_to_python(items[0]['since'])
    report.status = items[0]['status']
    report.complete = items[0]['complete']
    report.error = items[0]['error']
    report.total_response = len(items[0]['list'])

    for item_id in items[0]['list']:
        item = items[0]['list'][item_id]
        existing_item = get_existing_item(item_id)
        if not existing_item:
            #article = Article(sort_id=item['sort_id'], item_id=item['item_id'])
            article = Article(item_id=item['item_id'])
            logger.debug('Existing item NOT found for ' + item_id)
        else:
            article = existing_item
            logger.debug('Existing item found for ' + item_id)

        if existing_item:
            previous_status = existing_item.status
        # 0, 1, 2 - 1 if the item is archived - 2 if the item should be deleted
        article.status = item['status']
        if article.status == '0' and not existing_item:
            nr_added += 1
        elif article.status == '1' and not existing_item:
            nr_added += 1
            nr_read += 1
        elif article.status == '1':
            nr_read += 1
        elif article.status == '2' and not existing_item:
            nr_added += 1
            nr_deleted += 1
        elif article.status == '2':
            nr_deleted += 1

        #if not existing_item and not 'resolved_id' in item:
        if not 'resolved_id' in item:
            # Item was added and immediately deleted, or at least before we saw it
            logger.debug(safe_unicode(item['status']) + ' ' + safe_unicode(item['item_id']) + ' deleted')

            article.firstseen_status = item['status']
            article.firstseen_time = now
            try:
                article.firstseen_time_updated = unix_to_python(item['time_updated'])
            except KeyError:
                pass

            # If item didn't exist yet, add it (otherwise it's updated automagically)
            session.add(article)
            # Skip the rest of the loop
            continue

        logger.debug(safe_unicode(item['status']) + ' ' + safe_unicode(item['item_id']) + ' ' + safe_unicode(item['resolved_id']) + ' ' + unix_to_string(item['time_added']) + ' ' + unix_to_string(item['time_updated']) + ' ' + safe_unicode(item['resolved_url']))
        article.resolved_id = item['resolved_id']
        article.sort_id = item['sort_id']
        article.given_url = item['given_url']
        article.resolved_url = item['resolved_url']
        article.given_title = item['given_title']
        article.resolved_title = item['resolved_title']
        if existing_item and existing_item.favorite == 0 and item['favorite'] == '1':
            nr_favourited += 1
        elif existing_item == None and item['favorite'] == '1':
            nr_favourited += 1
        article.favorite = item['favorite']

        article.excerpt = item['excerpt']
        article.is_article = item['is_article']
        article.has_image = item['has_image']
        article.has_video = item['has_video']
        article.word_count = item['word_count']
        if 'tags' in item:
            article.tags = json.dumps(item['tags'])
        if 'authors' in item:
            article.authors = json.dumps(item['authors'])
        if 'images' in item:
            article.images = json.dumps(item['images'])
        if 'videos' in item:
            article.videos = json.dumps(item['videos'])
        if existing_item and existing_item.time_updated != unix_to_python(item['time_updated']):
            nr_updated += 1
        article.time_updated = unix_to_python(item['time_updated'])
        article.time_favorited = unix_to_python(item['time_favorited'])
        article.time_read = unix_to_python(item['time_read'])
        if not existing_item:
            article.firstseen_status = item['status']
            article.firstseen_time = now
            article.firstseen_time_updated = unix_to_python(item['time_updated'])

            # If item didn't exist yet, add it (otherwise it's updated automagically)
            session.add(article)

    report.nr_added = nr_added
    report.nr_read = nr_read
    report.nr_favourited = nr_favourited
    report.nr_deleted = nr_deleted
    report.nr_updated = nr_updated
    session.add(report)

    # Check what's pending
    #logger.debug('About to commit to DB:')
    #logger.debug(session.new)

    # Save to DB
    session.commit()

    debug_print(report.pretty_print())
    logger.info(report)


@cli.command()
def createdb():
    """
    Create the database
    """
    _create_tables()


@cli.command()
@click.option('--consumer_key', prompt='Your Consumer Key', help='Get it at https://getpocket.com/developer/')
def gettoken(consumer_key):
    """
    Get access token
    """
    # URL to redirect user to, to authorize your app
    redirect_uri = 'https://github.com/aquatix/pocketstats'
    try:
        request_token = Pocket.get_request_token(consumer_key=consumer_key, redirect_uri=redirect_uri)
        auth_url = Pocket.get_auth_url(code=request_token, redirect_uri=redirect_uri)
    except pocket.RateLimitException as e:
        # pocket.RateLimitException: User was authenticated, but access denied due to lack of permission or rate limiting. Invalid consumer key.
        print "Failed to get an access token, likely due to an invalid consumer key"
        print "Go to https://getpocket.com/developer/ and generate a key there"
        print ""
        sys.exit(1)
    print "Open the uri printed below in your browser and allow the application"
    print "Note the key you get in response, as that is your access_token"
    print ""
    print auth_url
    print ""


@cli.command()
def showstats():
    """
    Show statistics about the collection
    """
    session = get_db_connection()
    #session.query(Article).
    #items = session.query(extract('year', Article.time_read).label('year')).distinct().subquery()
    #items = session.query(extract('year', Article.time_read).label('year'), func.count(Article.id)).distinct().order_by('year')
    items = session.query(extract('year', Article.time_read).label('year'), func.count(Article.id)).group_by('year')
    for item in items:
        print item
    return

    items = session.query(extract('year', Article.time_read).label('year')).distinct()
    for item in items:
        print item

    per_date = session.query(func.count(Article.id), extract('date', Article.time_read).label('h')).group_by('h')
    for item in per_date:
        print item
    per_hour = session.query(extract('hour', Article.time_read).label('h')).group_by('h')
    for item in per_hour:
        print item


if not hasattr(main, '__file__'):
    """
    Running in interactive mode in the Python shell
    """
    print("Pocket stats running interactively in Python shell")

elif __name__ == '__main__':
    """
    Pocket stats is ran standalone, rock and roll
    """
    cli()
