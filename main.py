# -*- coding: utf-8 -*-


import csv
from contextlib import contextmanager
import datetime
import json
import os
import uuid
from collections import defaultdict

import jinja2
from jinja2 import Environment, FileSystemLoader
import bottle
from bottle import request, response
import sqlalchemy
from sqlalchemy.sql.expression import func

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
    prob_indexes = [93, 95, 106, 112, 115]
    ans = []
    for i, j in zip(prob_indexes[:-1], prob_indexes[1:]):
        label = i18n.text(i, language)
        # probs = [ i18n.text(x, language) for x in range(i + 1, j) ]
        probs = [ ]
        ans.append((label, probs))
    return ans

def is_test():
    curtime = datetime.datetime.utcnow()
    if curtime < datetime.datetime(2020, 5, 8, 12, 0, 0):
        return True
    else:
        return False


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
        enable_day1 = session.query(models.ExamPaper).filter_by(
                is_active=True, test_name='hard_day_1').first() is not None
        enable_day2 = session.query(models.ExamPaper).filter_by(
                is_active=True, test_name='hard_day_2').first() is not None
    return jinja_env.get_template('landing.html').render(
            uid=uid, enable_day1=enable_day1, enable_day2=enable_day2)


@bottle.get('/user/<uid>/prob_router')
def route(uid):
    s = request.query.get('submit')
    if s == 'Start Day 1':
        bottle.redirect('/user/{}/prob/jiwls'.format(uid))
    if s == 'Start Day 2':
        bottle.redirect('/user/{}/prob/oweiur'.format(uid))


@bottle.get('/user/<uid>/prob/<pid>')
def get_prob_page(uid, pid):
    msg = request.query.get('msg', '')
    language = request.query.get('lang', 'en')

    level = {
            'jiwls': 'hard_day_1',
            'oweiur': 'hard_day_2',
            }.get(pid)

    if not level:
        return 'Exam not started yet'


    if is_test():
        passcode = request.query.get('testonly', None)
        if passcode != 'soy un arrecho':
            return 'Exam not started yet'

    with session_scope() as session:
        user = session.query(models.User).filter_by(access_uuid=uid).first()
        if user is None:
            return 'Access Id not found'

        submissions_numbers = {s.prob_id for s in user.submissions}

        if is_test():
            start_time = datetime.datetime.utcnow()
        else:
            if level == 'hard_day_1':
                if user.start_timestamp is None:
                    start_time = datetime.datetime.utcnow()
                    session.query(models.User).filter_by(access_uuid=uid).update(
                            {'start_timestamp': datetime.datetime.utcnow()})
                else:
                    start_time = user.start_timestamp
            else:
                if user.day2_timestamp is None:
                    start_time = datetime.datetime.utcnow()
                    session.query(models.User).filter_by(access_uuid=uid).update(
                            {'day2_timestamp': datetime.datetime.utcnow()})
                else:
                    start_time = user.day2_timestamp

        statements = session.query(models.ExamPaper).filter_by(
                is_active=True, test_name=level).all()
        if not statements:
            return 'Exam not started yet'

        print([(s.language, s.is_active) for s in statements])
        problems = get_problems(language)
        end_time = start_time + datetime.timedelta(hours=5)
        current_time = datetime.datetime.utcnow()
        budget_secs = (end_time - current_time).total_seconds()
        start_number = 100 if level == 'hard_day_1' else 104
        return jinja_env.get_template('problems.html').render(
                user=user, msg=msg, problems=problems,
                lang=language,
                answer_lang=ANSWER_LANG,
                end_time=end_time, i18n=i18n, budget_secs=budget_secs,
                submissions_numbers=submissions_numbers,
                statements=statements,
                start_number=start_number,
                time_start_utc='{}:{}:{}'.format(
                    start_time.hour, start_time.minute, start_time.second))

@bottle.get('/submission')
def get_prob():
    lang = request.query.get('lang')
    prob_id = request.query.get('prob_id')
    grader = request.query.get('not_graded_by')
    if lang is None or prob_id is None:
        return {'status': 'miss argument'}
    with session_scope() as session:

        graded_by_this = {
            s.submission_id for s in 
            session.query(models.Score).filter_by(grader=grader)}

        c_solution = session.query(func.count(models.Score.uid), 
                models.Submission).outerjoin(models.Score).filter(
                models.Submission.prob_id == prob_id).filter(
                models.Submission.language == lang
                ).group_by(
                        models.Submission.uid).having(
                                func.count(models.Score.uid) <= 1)

        c, solution = None, None
        for c_sol in c_solution:
            if c_sol[1].uid not in graded_by_this:
                c, solution = c_sol
                break
        if c is None:
            return {'status': 'not_found'}

        return {
            'status': 'found',
            'link': solution.link,
            'prob_id': solution.prob_id,
            'lang': solution.language,
            'scores_count': c,
            'submission_id': solution.uid,
            'timestamp': solution.timestamp.isoformat(),
            'start_time': solution.user.start_timestamp.isoformat(),
        }


@bottle.post('/submission/<uid>/score')
def create_score(uid):
    score_prop = json.loads(request.body.read())
    print(score_prop)
    with session_scope() as session:
        new_score = models.Score()
        new_score.submission_id = uid
        new_score.comment = score_prop['comment']
        new_score.grader = score_prop['grader']
        new_score.score = score_prop['score']
        new_score.timestamp = datetime.datetime.utcnow()
        session.add(new_score)
        session.commit()
    return {'status': 'success'}


@bottle.post('/upload_solution/<uid>')
def recv_solution(uid):
    prob_id = int(request.forms.get('prob_id'))
    link = request.forms.get('link')
    user_id = int(request.forms.get('user_id'))
    upload = request.files.get('upload', None)
    language = request.forms.get('language')
    timestamp = datetime.datetime.utcnow()
    level = 'jiwls' if prob_id <= 104 else 'oweiur'
    with session_scope() as session:
        prev_submission = session.query(models.Submission).filter_by(
                user_id=user_id, prob_id=prob_id).first()

        redirect_url = '/user/{}/prob/{}?msg=success'.format(uid, level)
        if prev_submission:
            filename = os.path.basename(prev_submission.link)
            upload.save(os.path.join(config.FILE_SAVE_DIR, filename),
                        overwrite=True)
            session.query(models.Submission).filter_by(
                    uid=prev_submission.uid).update(
                            {'timestamp': timestamp})
            session.commit()
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
        scores = dict(session.query(
                models.Score.submission_id,
                func.count(models.Score.uid)).group_by(
                        models.Score.submission_id))
        submissions = sorted(
                session.query(models.Submission, models.User).filter(
                models.Submission.user_id == models.User.uid),
                key=lambda x: scores.get(x[0].uid, 0))
        return jinja_env.get_template('submissions.html'
            ).render(submissions=submissions, scores=scores)

@bottle.get('/supersecreteurl/vitafusion/scores')
def all_scores():
    with session_scope() as session:
        submissions_scores = session.query(models.Submission, models.Score).filter(
                models.Submission.uid == models.Score.submission_id).filter(
                models.Submission.prob_id < 100).all()
        grouped = defaultdict(list)
        for sub, score in submissions_scores:
            grouped[sub.uid].append((sub, score))

        def diff_score(sub_score_list):
            scores = list(map(lambda x: x[1].score, sub_score_list))
            return -(max(scores) - min(scores))

        def should_keep_review(submission):
            # submission is list of tuple of (submission, score)
            num_scores = len(submission)
            scores = [s[1].score for s in submission if s[1].score != -1]
            if not scores:  # score is empty i.e. all -1
                return True
            if num_scores <= 1:
                return True
            if max(scores) - min(scores) > 2:
                return True
            if max(scores) == 7: 
                if min(scores) != 7:
                    return True
                if num_scores < 2:
                    return True
            if submission[0][0].language.lower() == 'estonian':
                return True
            return False

        filtered = filter(should_keep_review, grouped.values())
        sorted_grouped = sorted(filtered, key=diff_score)
        return jinja_env.get_template('resolve_score.html'
            ).render(submissions=sorted_grouped)


@bottle.get('/supersecreteurl/gradingpage')
def grading_page():
    return jinja_env.get_template('grading.html').render(answer_langs=ANSWER_LANG)


def insert_users_from_file(path):
    with open(path) as f:
        content = list(f.read().strip().split())
        with session_scope() as session:
            users = session.query(models.User).filter(
                    models.User.email.in_(content))
            existing = {u.email for u in users}
            for e in content:
                if e in existing:
                    continue
                u = models.User()
                u.email = e
                access = uuid.uuid4().hex
                u.access_uuid = access
                session.add(u)
                print('user', e, access)
            session.commit()


def export_users(path):
    with open('/home/servidor/hardexam.csv') as x:
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

@bottle.get('/supersecreteurl/blahblah/problem_links')
def problem_links():
    exam_names = ["hard_day_1", "hard_day_2"]
    with session_scope() as session:
        all_problems = list(session.query(models.ExamPaper))
        return jinja_env.get_template('exam_links.html').render(
                all_problems=all_problems,
                languages=ANSWER_LANG,
                levels=exam_names)

@bottle.post('/supersecreteurl/blahblah/problem_links')
def new_problem_links():
    language = request.forms.get('language')
    exam_name = request.forms.get('test_name')
    link = request.forms.get('link')

    with session_scope() as session:
        exam = models.ExamPaper()
        exam.language = language
        exam.link = link
        exam.test_name = exam_name
        session.add(exam)
        session.commit()
    bottle.redirect('/supersecreteurl/blahblah/problem_links')


@bottle.put('/save_resolve/<uid>')
def save_result(uid):
    data = json.loads(request.body.read())
    uid = int(uid)
    with session_scope() as session:
        prev = session.query(models.ResolvedScore).filter_by(uid=uid).first()
        if prev:
            session.query(models.ResolvedScore).filter_by(uid=uid).update(
                    data)
        else:
            new = models.ResolvedScore()
            new.uid = uid
            new.comment = data['comment']
            new.grader = data['grader']
            new.score = data['score']
            session.add(new)
        session.commit() 
        return {'status': 'success'}
            

@bottle.put('/exam/<uid>')
def modify_exam(uid):
    content = json.loads(request.body.read())
    with session_scope() as session:
        print(content)
        session.query(models.ExamPaper).filter_by(uid=uid).update(
                content)
        session.commit()
        return {'status': 'success'}


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
