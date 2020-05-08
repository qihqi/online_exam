# -*- coding: utf-8 -*-


import csv
from contextlib import contextmanager
import datetime
import os
import uuid

import jinja2
from jinja2 import Environment, FileSystemLoader
import bottle
from bottle import request, response
import sqlalchemy

import models
import config

TESTONLY = True
FILE_SAVE_DIR = '/tmp'

engine = sqlalchemy.create_engine(config.CONN_STRING)
Session = sqlalchemy.orm.sessionmaker(bind=engine)
jinja_env = Environment(loader=FileSystemLoader('template'))


ANSWER_LANG = sorted("""
English
Spanish
French
Arabic
Russian
German
Italian
Thai
Hungarian
Estonian
""".strip().split('\n'))

question_links = {
        'ar': 'https://drive.google.com/file/d/19acDQBnU6w1b3RfaoqnDjX_vu10jUyUM/view?usp=sharing',
        'de_DE': 'https://drive.google.com/file/d/1KCsjhIJow90PSn6PDkeBL2_-hQloH8tP/view?usp=sharing',
        'ee': 'https://drive.google.com/file/d/1lrPGVVxc7eAZ0tzlx8Q042GCpH4f3DNl/view?usp=sharing',
        'en': 'https://drive.google.com/file/d/1Z1pabuOsFnIidUbfnPF3VhA5SOfzDvOk/view?usp=sharing',
        'es_ES': 'https://drive.google.com/file/d/1V3mRHr7VMiXYtsnHEiZ88m6UxgWeAPd8/view?usp=sharing',
        'fr_FR': 'https://drive.google.com/file/d/1o30XQJf89stbcWtfHGSWaFxsmOBCxJ2c/view?usp=sharing',
        'hu':'https://drive.google.com/file/d/1Qs4V_oT9NhrZzZiYLQ0UBg6YnOhuYNtq/view?usp=sharing',
        'it': 'https://drive.google.com/file/d/1L21RXwUM3bExf7Wi2cFLezhBLWzc0M3z/view?usp=sharing',
        'uk': 'https://drive.google.com/file/d/1FreQgETTGxP1Y3ndKSHxM0QshcK3cebo/view?usp=sharing',
        'fa': 'https://drive.google.com/file/d/1SFcfQx_6hHr47NMtmzGHccuJGmOR7TRy/view?usp=sharing',
        'ru': 'https://drive.google.com/file/d/17hIoFGcoJ-JzL_VipGQeK6clYCVgF1sZ/view?usp=sharing',
        'th': 'https://drive.google.com/file/d/1mQVsbl6vymaTdI_Cybd-Kg1-HT69m-NZ/view?usp=sharing',
        'uk': 'https://drive.google.com/file/d/1BPHdBP5H3hQFaxDwPVq2M6uMYHEuxkvf/view?usp=sharing',
        }



class I18nManager(object):

    def __init__(self, csv_path):
        with open(csv_path) as f:
            reader = csv.reader(f)
            self._contents = list(reader)
            self.all_locales = self._contents[0]
            self.locales_to_index = {
                    locale : i for i, locale in enumerate(self.all_locales)}
            self.name_to_index = {
                    locale : i for i, locale in enumerate(self._contents[1])}

    def text(self, position, locale):
        lpos = self.locales_to_index[locale]
        return self._contents[position - 1][lpos]

    def lang_name(self, locale):
        if locale == 'ee':
            return 'Estonian'
        return self.text(2, locale)

    def locale_name(self, name):
        return self._contents[0][self.name_to_index[name]]


i18n = I18nManager(config.TEXT_STR)


def get_problems(language):
    prob_indexes = [93, 95, 106, 112, 115, 124, 129]
    ans = []
    for i, j in zip(prob_indexes[:-1], prob_indexes[1:]):
        label = i18n.text(i, language)
        # probs = [ i18n.text(x, language) for x in range(i + 1, j) ]
        probs = [ ]
        ans.append((label, probs))
    return ans


@contextmanager
def session_scope():
    """Provide a transactional scope around a series of operations."""
    session = Session()
    try:
        yield session
        session.commit()
    except:
        session.rollback()
        raise
    finally:
        session.close()


@bottle.get('/static/<path:path>')
def static(path):
    return bottle.static_file(path, root='static')


def index():
    return bottle.static_file('mock.html', root='static')

@bottle.get('/user/<uid>')
def get_landing_page(uid):
    with session_scope() as session:
        user = session.query(models.User).filter_by(access_uuid=uid).first()
        if user is None:
            return 'Access Id not found'
    return jinja_env.get_template('landing.html').render(
            uid=uid)


@bottle.get('/user/<uid>/prob')
def get_prob_page(uid):
    msg = request.query.get('msg', '')
    hard_level = request.query.get('hard_level', 'easy')
    language = request.query.get('lang', 'en')

    if TESTONLY:
        passcode = request.query.get('testonly', None)
        if passcode != 'soy un arrecho':
            return 'Exam not started yet'

    with session_scope() as session:
        user = session.query(models.User).filter_by(access_uuid=uid).first()
        if user is None:
            return 'Access Id not found'

        submissions_numbers = {s.prob_id for s in user.submissions}

        print('sub', submissions_numbers)
        if TESTONLY:
            start_time = datetime.datetime.utcnow()
        else:
            if user.start_timestamp is None:
                start_time = datetime.datetime.utcnow()
                session.query(models.User).filter_by(access_uuid=uid).update(
                        {'start_timestamp': datetime.datetime.utcnow()})
            else:
                start_time = user.start_timestamp

        problems = get_problems(language)
        end_time = start_time + datetime.timedelta(hours=5, minutes=30)
        current_time = datetime.datetime.utcnow()
        budget_secs = (end_time - current_time).total_seconds()
        return jinja_env.get_template('problems.html').render(
                user=user, msg=msg, problems=problems,
                lang=language, hard_level=hard_level,
                answer_lang=ANSWER_LANG,
                exam_links=question_links,
                end_time=end_time, i18n=i18n, budget_secs=budget_secs,
                submissions_numbers=submissions_numbers)


@bottle.post('/upload_solution/<uid>')
def recv_solution(uid):
    prob_id = int(request.forms.get('prob_id'))
    link = request.forms.get('link')
    user_id = int(request.forms.get('user_id'))
    upload = request.files.get('upload', None)
    language = request.forms.get('language')
    timestamp = datetime.datetime.utcnow()
    with session_scope() as session:
        prev_submission = session.query(models.Submission).filter_by(
                user_id=user_id, prob_id=prob_id).first()

        redirect_url = '/user/{}/prob?msg=success'.format(uid)
        if prev_submission:
            filename = os.path.basename(prev_submission.link)
            upload.save(os.path.join(config.FILE_SAVE_DIR, filename),
                        overwrite=True)
            session.query(models.Submission).filter_by(
                    user_id=user_id, prob_id=prob_id).update(
                            {'timestamp': timestamp})
        else:
            if upload is not None:
                if link:
                    bottle.redirect(
                        ('/user/{}/prob?msg=cannot+'
                        'upload+file+and+link+at+the+same+time').format(uid))
                orig_name, ext = os.path.splitext(upload.filename)
                new_filename = uuid.uuid4().hex + ext
                upload.save(os.path.join(config.FILE_SAVE_DIR, new_filename))
                link = os.path.join(config.STATIC_FILE_URL, new_filename)
            sub = models.Submission()
            sub.link = link
            sub.user_id = user_id
            sub.prob_id = prob_id
            sub.language = language
            sub.timestamp = timestamp
            session.add(sub)
            session.commit()
        return bottle.redirect(redirect_url)


@bottle.get('/supersecreteurl/nadielosabra/asjfsadjflsdjl')
def all_solutions():
    with session_scope() as session:
        submissions = session.query(models.Submission, models.User).filter(
                models.Submission.user_id == models.User.uid)
        return jinja_env.get_template('submissions.html'
            ).render(submissions=submissions)

def insert_users_from_file(path):
    with open(path) as f:
        content = dict(csv.reader(f))
        with session_scope() as session:
            users = session.query(models.User).filter(
                    models.User.email.in_(content.keys()))
            existing = {u.email for u in users}
            for e, c in content.items():
                if e in existing:
                    continue
                u = models.User()
                u.email = e
                u.access_uuid = c[-32:]
                session.add(u)
                print('user', e, c, len(c))

def export_users(path):
    with open('/home/han/Downloads/easy_exam.csv.csv') as x:
        emails = set(x.read().split())
    with open(path, 'w', newline='') as f:
        csv_writer = csv.writer(f)
        with session_scope() as session:
            users = session.query(models.User).filter(
                    models.User.email.in_(emails))
            for user in users:
                csv_writer.writerow((user.email, 
                        'http://exam.gqmo.org/user/{}'.format(
                            user.access_uuid)))

def make_one_user(email): 
    with session_scope() as session:
        user = session.query(models.User).filter(
                models.User.email == email).first()
        if user is not None:
            print('already exists', user.access_uuid)
            return
        user = models.User()
        user.email = email
        user.access_uuid = uuid.uuid4().hex
        session.add(user)
        print('created: ', user.access_uuid)


application = bottle.default_app()

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--insert_users', default='')
    parser.add_argument('--create_db', default='')
    parser.add_argument('--export_users', default='')
    parser.add_argument('--new_user', default='')
    args = parser.parse_args()
    if args.create_db:
        models.Base.metadata.create_all(engine)
    elif args.insert_users:
        insert_users_from_file(args.insert_users)
    elif args.export_users:
        export_users(args.export_users)
    elif args.new_user:
        make_one_user(args.new_user)
    else:
        bottle.run(host='0.0.0.0', port=8099)
