import datetime
from time import mktime
import json
import logging
import sys
import __main__ as main
import pocket
from pocket import Pocket
from utilkit import datetimeutil, printutil, stringutil
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


def debug_print(string):
    if DEBUG:
        print string


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

    def get_tags(self):
        result = []
        for tag in json.loads(self.tags):
            result.append(tag)
        return result

    def __str__(self):
        #return u'[' + str(self.item_id) + '] ' + self.resolved_title + ' - ' + self.resolved_url
        return u'[' + str(self.item_id) + '] ' + str(self.resolved_url)


    def __unicode__(self):
        return self.__str__()


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
    time_since_unix = Column(Integer)
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
    # json summary of the changed articles (added, read, deleted, fav'd, updated)
    changed_articles = Column(Text)


    @property
    def net_result(self):
        return self.nr_added - self.nr_read - self.nr_deleted


    def pretty_print(self):
        """
        Return a pretty overview of the report, usable for printing as import result
        """
        data = [['update at', datetimeutil.datetime_to_string(self.time_updated)], ['total in response', str(self.total_response)], ['updated', str(self.nr_updated)], ['added', str(self.nr_added)], ['read', str(self.nr_read)], ['favourited', str(self.nr_favourited)], ['deleted', str(self.nr_deleted)], ['net result', str(self.net_result)]]
        result = ''
        col_width = max(len(word) for row in data for word in row) + 2  # padding
        for row in data:
            result += u''.join(word.ljust(col_width) for word in row) + '\n'
        return result


    def print_changed_articles(self, session):
        """
        Return a pretty overview of the articles that were added/read/etc
        """
        changed_articles = json.loads(self.changed_articles)
        result = u''
        for changetype in changed_articles:
            idlist = changed_articles[changetype]
            result += u'\n== ' + changetype + ' ======\n'
            for item_id in idlist:
                this_item = get_existing_item(session, item_id)
                result += u'' + str(this_item) + '\n'
        return result


    def __str__(self):
        return u'Update at ' + datetimeutil.datetime_to_string(self.time_updated) + '; total in response: ' + str(self.total_response) + ', nr_updated: ' + str(self.nr_updated) + ', nr_added: ' + str(self.nr_added) + ', nr_read: ' + str(self.nr_read) + ', nr_favourited: ' + str(self.nr_favourited) + ', nr_deleted: ' + str(self.nr_deleted)


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
        time_since_unix, report_id = session.query(Report.time_since_unix, Report.id).order_by(desc(Report.time_since))[0]
        #return mktime(time_since.timetuple())
        return time_since_unix
    except IndexError:
        return None


def get_existing_item(session, item_id):
    """
    Returns the item with item_id if already in DB, otherwise None
    """
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


def nr_total(session):
    return get_count(session.query(Article.id))


def nr_unread(session):
    return get_count(session.query(Article).filter(Article.status == 0))


def nr_read(session):
    return get_count(session.query(Article).filter(Article.status == 1))


def nr_deleted(session):
    return get_count(session.query(Article).filter(Article.status == 2))


def nr_favourited(session):
    return get_count(session.query(Article).filter(Article.favorite == 1))


def get_read_progressbar(session):
    COLUMNS = 40
    items_total = nr_total(session)
    items_read = nr_read(session)
    return str(items_read) + '/' + str(items_total) + '  ' + printutil.progress_bar(items_total, items_read, COLUMNS, '.', '#', True)


def updatestats_since_last(logger, session, last_time):
    """
    Get the changes since last time from the Pocket API
    """
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
    changed_articles = {'added': [], 'read': [], 'deleted': [], 'favourited': [], 'updated': []}
    report.time_since = datetimeutil.unix_to_python(items[0]['since'])
    report.time_since_unix = items[0]['since']
    report.status = items[0]['status']
    report.complete = items[0]['complete']
    report.error = items[0]['error']
    report.total_response = len(items[0]['list'])

    for item_id in items[0]['list']:
        item = items[0]['list'][item_id]
        existing_item = get_existing_item(session, item_id)
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
        try:
            if article.status == '0' and not existing_item:
                nr_added += 1
                changed_articles['added'].append(item['item_id'])
            elif article.status == '1' and not existing_item:
                nr_added += 1
                nr_read += 1
                changed_articles['added'].append(item['item_id'])
                changed_articles['read'].append(item['item_id'])
            elif article.status == '1':
                nr_read += 1
                changed_articles['read'].append(item['item_id'])
            elif article.status == '2' and not existing_item:
                nr_added += 1
                nr_deleted += 1
                changed_articles['added'].append(item['item_id'])
                changed_articles['deleted'].append(item['item_id'])
            elif article.status == '2':
                nr_deleted += 1
                changed_articles['deleted'].append(item['item_id'])
        except KeyError:
            logger.info('No resolved_id found')

        #if not existing_item and not 'resolved_id' in item:
        if not 'resolved_id' in item:
            # Item was added and immediately deleted, or at least before we saw it
            logger.debug(stringutil.safe_unicode(item['status']) + ' ' + stringutil.safe_unicode(item['item_id']) + ' deleted')

            article.item_id = item['item_id']
            article.firstseen_status = item['status']
            article.firstseen_time = now
            try:
                article.firstseen_time_updated = datetimeutil.unix_to_python(item['time_updated'])
            except KeyError:
                pass

            # If item didn't exist yet, add it (otherwise it's updated automagically)
            session.add(article)
            # Skip the rest of the loop
            continue

        logger.debug(stringutil.safe_unicode(item['status']) + ' ' + stringutil.safe_unicode(item['item_id']) + ' ' + stringutil.safe_unicode(item['resolved_id']) + ' ' + datetimeutil.unix_to_string(item['time_added']) + ' ' + datetimeutil.unix_to_string(item['time_updated']) + ' ' + stringutil.safe_unicode(item['resolved_url']))
        article.resolved_id = item['resolved_id']
        article.sort_id = item['sort_id']
        article.given_url = item['given_url']
        article.resolved_url = item['resolved_url']
        article.given_title = item['given_title']
        article.resolved_title = item['resolved_title']
        if existing_item and existing_item.favorite == 0 and item['favorite'] == '1':
            nr_favourited += 1
            changed_articles['favourited'].append(item['item_id'])
        elif existing_item == None and item['favorite'] == '1':
            nr_favourited += 1
            changed_articles['favourited'].append(item['item_id'])
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
        if existing_item and existing_item.time_updated != datetimeutil.unix_to_python(item['time_updated']):
            nr_updated += 1
            changed_articles['updated'].append(item['item_id'])
        article.time_updated = datetimeutil.unix_to_python(item['time_updated'])
        article.time_favorited = datetimeutil.unix_to_python(item['time_favorited'])
        article.time_read = datetimeutil.unix_to_python(item['time_read'])
        if not existing_item:
            article.firstseen_status = item['status']
            article.firstseen_time = now
            article.firstseen_time_updated = datetimeutil.unix_to_python(item['time_updated'])

            # If item didn't exist yet, add it (otherwise it's updated automagically)
            session.add(article)

    report.nr_added = nr_added
    report.nr_read = nr_read
    report.nr_favourited = nr_favourited
    report.nr_deleted = nr_deleted
    report.nr_updated = nr_updated
    report.changed_articles = json.dumps(changed_articles)
    #debug_print(report.changed_articles)
    session.add(report)

    # Check what's pending
    #logger.debug('About to commit to DB:')
    #logger.debug(session.new)

    # Save to DB
    session.commit()

    return report


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
    print datetimeutil.unix_to_python(last_time)
    debug_print('Previous update: ' + datetimeutil.unix_to_string(last_time))

    previously_unread = nr_unread(session)

    report = updatestats_since_last(logger, session, last_time)

    debug_print(report.pretty_print())

    if report.net_result > 0:
        debug_print('More items added than read or deleted')
    elif report.net_result == 0:
        debug_print('Stagnating')
    else:
        # Calculate number of days it will take to finish the backlog at this rate
        #timedelta
        #days = last_time
        debug_print('Slowly but surely reading away your backlog')

    debug_print(get_read_progressbar(session))

    debug_print(report.print_changed_articles(session))
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
    # Size of progress-bar
    COLUMNS = 40
    result = []

    session = get_db_connection()
    #session.query(Article).
    #items = session.query(extract('year', Article.time_read).label('year')).distinct().subquery()
    #items = session.query(extract('year', Article.time_read).label('year'), func.count(Article.id)).distinct().order_by('year')

    # Numbers
    items_total = nr_total(session)
    items_read = nr_read(session)
    items_unread = nr_unread(session)
    items_favourited = nr_favourited(session)
    items_deleted = nr_deleted(session)

    result.append(['Total items', str(items_total)])
    result.append(['Total read', str(items_read)])
    result.append(['Total unread', str(items_unread)])
    result.append(['Total favourited', str(items_favourited)])
    result.append(['Total deleted', str(items_deleted)])
    result.append([])

    # Progress bar
    result.append(['progress', printutil.progress_bar(items_total, items_read, COLUMNS, '.', '#', True)])
    result.append(['favourites', printutil.progress_bar(items_total, items_favourited, COLUMNS, ' ', '*')])

    result.append([])

    # Read articles per yer
    result.append(['year', 'amount of articles read'])
    items = session.query(extract('year', Article.time_read).label('year'), func.count(Article.id)).group_by('year')
    for item in items:
        if item[0] == None:
            result.append(['unknown', str(item[1])])
        elif item[0] == 1970:
            result.append(['unread', str(item[1])])
        else:
            result.append([str(item[0]), str(item[1])])

    result.append([])
    print(printutil.to_smart_columns(result))

    # List of number of items read, per date
    items_read = session.query(func.date(Article.time_read).label('thedate'), func.count(Article.id)).group_by('thedate')
    # firstseen_time_updated comes as close to 'time added' as we can get from the Pocket API
    items_added = session.query(func.date(Article.firstseen_time_updated).label('thedate'), func.count(Article.id)).group_by('thedate')
    #for item in items_added:
    #    print item
    # TODO: plot added-vs-read graph
    items_added_per_month = session.query(extract('year', Article.firstseen_time_updated).label('year'), extract('month', Article.firstseen_time_updated).label('month'), func.count(Article.id)).group_by('year', 'month')
    items_read_per_month = session.query(extract('year', Article.time_read).label('year'), extract('month', Article.time_read).label('month'), func.count(Article.id)).group_by('year', 'month')
    read_vs_added = printutil.x_vs_y(items_read_per_month, items_added_per_month, filter_none=True)
    #for item in read_vs_added:
    #    result.append(item)
    print read_vs_added

    # Tags
    # TODO: loop over Articles, get amount of articles/tag

    # Finally, print the stats
    #print(printutil.to_smart_columns(result))
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


@cli.command()
def showprogressbar():
    session = get_db_connection()
    print get_read_progressbar(session)


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
