from CTFd.plugins.challenges import CTFdStandardChallenge, CHALLENGE_CLASSES
from CTFd.plugins import register_plugin_assets_directory
from CTFd.plugins.keys import get_key_class
from CTFd.models import db,Awards, WrongKeys, Solves, Keys, Challenges, Files, Tags, Teams, Hints
from CTFd import utils
from flask import session, jsonify, request, render_template
from sqlalchemy.sql import and_
import datetime
import math
from sqlalchemy.sql.expression import union_all

class TimeDecaySolves(db.Model):
    __table_args__ = (db.UniqueConstraint('chalid', 'teamid'), {})
    id = db.Column(db.Integer, primary_key=True)
    chalid = db.Column(db.Integer, db.ForeignKey('challenges.id'))
    teamid = db.Column(db.Integer, db.ForeignKey('teams.id'))
    decayed_value = db.Column(db.Integer)

    def __init__(self, chalid, teamid, decayed_value):
        self.chalid = chalid
        self.teamid = teamid
        self.decayed_value = decayed_value

    def __repr__(self):
        return '<time-decay-solve {}, {}, {}, {}, {}, {}>'.format(self.id, self.chalid, self.teamid, self.decayed_value)


class TimeDecayChallenge(CTFdStandardChallenge):
    id = "time-decay"  # Unique identifier used to register challenges
    name = "time-decay"  # Name of a challenge type
    templates = {  # Handlebars templates used for each aspect of challenge editing & viewing
        'create': '/plugins/ctfd-time-decay-plugin/assets/time-decay-challenge-create.njk',
        'update': '/plugins/ctfd-time-decay-plugin/assets/time-decay-challenge-update.njk',
        'modal': '/plugins/ctfd-time-decay-plugin/assets/time-decay-challenge-modal.njk',
    }
    scripts = {  # Scripts that are loaded when a template is loaded
        'create': '/plugins/ctfd-time-decay-plugin/assets/time-decay-challenge-create.js',
        'update': '/plugins/ctfd-time-decay-plugin/assets/time-decay-challenge-update.js',
        'modal': '/plugins/ctfd-time-decay-plugin/assets/time-decay-challenge-modal.js',
    }

    @staticmethod
    def create(request):
        """
        This method is used to process the challenge creation request.

        :param request:
        :return:
        """
        # Create challenge
        chal = TimeDecay(
            name=request.form['name'],
            description=request.form['description'],
            category=request.form['category'],
            type=request.form['chaltype'],
            initial=request.form['initial'],
            omega=request.form['omega'],
        )

        if 'hidden' in request.form:
            chal.hidden = True
        else:
            chal.hidden = False

        max_attempts = request.form.get('max_attempts')
        if max_attempts and max_attempts.isdigit():
            chal.max_attempts = int(max_attempts)

        db.session.add(chal)
        db.session.commit()

        flag = Keys(chal.id, request.form['key'], request.form['key_type[0]'])
        if request.form.get('keydata'):
            flag.data = request.form.get('keydata')
        db.session.add(flag)

        db.session.commit()

        files = request.files.getlist('files[]')
        for f in files:
            utils.upload_file(file=f, chalid=chal.id)

        db.session.commit()

    @staticmethod
    def value(challenge):
        # Check if any team has solved the challenge
        solved = Solves.query.filter_by(chalid=challenge.id).order_by(Solves.date.asc()).first()
        if solved is None:
            return challenge.initial

        # Check if the current team has solved it
        if utils.authed():
            teamid = session['id']
            solved_by_team = Solves.query.filter(and_(Solves.chalid==challenge.id, Solves.teamid==teamid)).first()
            if solved_by_team is not None:
                time_decay_solved = TimeDecaySolves.query.filter(and_(TimeDecaySolves.chalid==challenge.id, TimeDecaySolves.teamid==teamid)).first_or_404()
                return time_decay_solved.decayed_value

        # Return value if challenge gets solved now
        return TimeDecayChallenge.get_decayed_scores(challenge.initial, challenge.omega, solved.date)

    @staticmethod
    def value_for_team(challid, teamid):
        time_decay_solved = TimeDecaySolves.query.filter(and_(TimeDecaySolves.chalid==challid, TimeDecaySolves.teamid==teamid)).first()
        if time_decay_solved is None:
            return 0
        return time_decay_solved.decayed_value

    @staticmethod
    def get_decayed_scores(initial, omega, first_solve_time):
        time_delta = (datetime.datetime.utcnow() - first_solve_time).total_seconds()
        return math.floor(initial * (0.5 ** (time_delta / omega)))

    @staticmethod
    def read(challenge):
        """
        This method is in used to access the data of a challenge in a format processable by the front end.

        :param challenge:
        :return: Challenge object, data dictionary to be returned to the user
        """
        challenge = TimeDecay.query.filter_by(id=challenge.id).first()

        data = {
            'id': challenge.id,
            'name': challenge.name,
            'value': TimeDecayChallenge.value(challenge),
            'initial': challenge.initial,
            'omega': challenge.omega,
            'description': challenge.description,
            'category': challenge.category,
            'hidden': challenge.hidden,
            'max_attempts': challenge.max_attempts,
            'type': challenge.type,
            'type_data': {
                'id': TimeDecayChallenge.id,
                'name': TimeDecayChallenge.name,
                'templates': TimeDecayChallenge.templates,
                'scripts': TimeDecayChallenge.scripts,
            }
        }
        return challenge, data

    @staticmethod
    def update(challenge, request):
        """
        This method is used to update the information associated with a challenge. This should be kept strictly to the
        Challenges table and any child tables.

        :param challenge:
        :param request:
        :return:
        """
        challenge = TimeDecay.query.filter_by(id=challenge.id).first()

        challenge.name = request.form['name']
        challenge.description = request.form['description']
        challenge.value = 0
        challenge.initial = request.form['initial']
        challenge.omega = request.form['omega']
        challenge.max_attempts = int(request.form.get('max_attempts', 0)) if request.form.get('max_attempts', 0) else 0
        challenge.category = request.form['category']
        challenge.hidden = 'hidden' in request.form
        db.session.commit()
        db.session.close()

    @staticmethod
    def delete(challenge):
        """
        This method is used to delete the resources used by a challenge.

        :param challenge:
        :return:
        """
        WrongKeys.query.filter_by(chalid=challenge.id).delete()
        TimeDecaySolves.query.filter_by(chalid=challenge.id).delete()
        Solves.query.filter_by(chalid=challenge.id).delete()
        Keys.query.filter_by(chal=challenge.id).delete()
        files = Files.query.filter_by(chal=challenge.id).all()
        for f in files:
            utils.delete_file(f.id)
        Files.query.filter_by(chal=challenge.id).delete()
        Tags.query.filter_by(chal=challenge.id).delete()
        Hints.query.filter_by(chal=challenge.id).delete()
        Challenges.query.filter_by(id=challenge.id).delete()
        TimeDecay.query.filter_by(id=challenge.id).delete()
        db.session.commit()

    @staticmethod
    def solve(team, chal, request):
        """
        This method is used to insert TimeDecaySolves into the database in order to mark a challenge as solved.

        :param team: The Team object from the database
        :param chal: The Challenge object from the database
        :param request: The request the user submitted
        :return:
        """
        provided_key = request.form['key'].strip()

        # Record current value for the challenge
        value = TimeDecayChallenge.value(chal)
        solve = Solves(teamid=team.id, chalid=chal.id, ip=utils.get_ip(req=request), flag=provided_key)
        db.session.add(solve)
        time_decay_solve = TimeDecaySolves(teamid=team.id, chalid=chal.id, decayed_value=value)
        db.session.add(time_decay_solve)
        db.session.commit()
        db.session.close()

class TimeDecay(Challenges):
    __mapper_args__ = {'polymorphic_identity': 'time-decay'}
    id = db.Column(None, db.ForeignKey('challenges.id'), primary_key=True)
    initial = db.Column(db.Integer)
    omega = db.Column(db.Integer)

    def __init__(self, name, description, category, type='time-decay', initial=10000, omega=60000):
        self.name = name
        self.description = description
        self.value = 0
        self.category = category
        self.type = type
        self.initial = initial
        self.omega = omega

def time_decay_score(self, admin=False):
    return db.session.query(db.func.sum(TimeDecaySolves.decayed_value)).filter_by(teamid=self.id).first()[0]

def solves_private_endpoint():
    if not utils.authed():
        return jsonify({'solves': []})
    solves_public_endpoint(session['id'])

def solves_public_endpoint(teamid):
    solves = Solves.query.filter_by(teamid = teamid)
    time_decay_solves = TimeDecaySolves.query.filter_by(teamid = teamid)
    db.session.close()

    response = {'solves': []}
    for solve in solves:
        value = 0
        for v in time_decay_solves:
            if v.chalid == solve.chalid:
                value = v.decayed_value
        response['solves'].append({
            'chal': solve.chal.name,
            'chalid': solve.chalid,
            'team': solve.teamid,
            'value': value,
            'category': solve.chal.category,
            'time': utils.unix_time(solve.date)
        })
    response['solves'].sort(key=lambda k: k['time'])
    return jsonify(response)

def team_endpoint(teamid):
    if utils.get_config('workshop_mode'):
        abort(404)

    if utils.get_config('view_scoreboard_if_utils.authed') and not utils.authed():
        return redirect(url_for('auth.login', next=request.path))
    errors = []
    freeze = utils.get_config('freeze')
    user = Teams.query.filter_by(id=teamid).first_or_404()
    solves = Solves.query.filter_by(teamid=teamid)
    awards = Awards.query.filter_by(teamid=teamid)

    place = user.place()
    score = user.score()

    if freeze:
        freeze = utils.unix_time_to_utc(freeze)
        if teamid != session.get('id'):
            solves = solves.filter(Solves.date < freeze)
            awards = awards.filter(Awards.date < freeze)

    solves = solves.all()
    awards = awards.all()
    time_decay_solves = TimeDecaySolves.query.filter_by(teamid=teamid).all()

    db.session.close()

    if utils.hide_scores() and teamid != session.get('id'):
        errors.append('Scores are currently hidden')

    if errors:
        return render_template('team.html', team=user, errors=errors)

    # pass decayed_value
    for s in solves:
        for t in time_decay_solves:
            if t.chalid == s.chalid:
                s.decayed_value = t.decayed_value

    if request.method == 'GET':
        return render_template('team.html', solves=solves, awards=awards, team=user, score=score, place=place, score_frozen=utils.is_scoreboard_frozen())
    elif request.method == 'POST':
        json = {'solves': []}
        for x in solves:
            json['solves'].append({'id': x.id, 'chal': x.chalid, 'team': x.teamid, 'decayed_value': TimeDecayChallenge.value_for_team(x.chalid, x.teamid)})
        return jsonify(json)

def who_solved_endpoint(chalid):
    response = {'teams': []}
    if utils.hide_scores():
        return jsonify(response)
    solves = Solves.query.join(Teams, Solves.teamid == Teams.id).filter(Solves.chalid == chalid, Teams.banned == False).order_by(Solves.date.asc())
    for solve in solves:
        response['teams'].append({'id': solve.team.id, 'name': solve.team.name, 'date': solve.date,
            'decayed_value': TimeDecayChallenge.value_for_team(chalid, solve.team.id)})
    return jsonify(response)

def get_standings_monkey_patch(admin=False, count=None):
    """
    Get team standings as a list of tuples containing team_id, team_name, and score e.g. [(team_id, team_name, score)].

    Ties are broken by who reached a given score first based on the solve ID. Two users can have the same score but one
    user will have a solve ID that is before the others. That user will be considered the tie-winner.

    Challenges & Awards with a value of zero are filtered out of the calculations to avoid incorrect tie breaks.
    """
    scores = db.session.query(
        Solves.teamid.label('teamid'),
        db.func.sum(TimeDecaySolves.decayed_value).label('score'),
        db.func.max(Solves.id).label('id'),
        db.func.max(Solves.date).label('date')
    ).join(TimeDecaySolves, and_(Solves.teamid == TimeDecaySolves.teamid, Solves.chalid == TimeDecaySolves.chalid))\
        .group_by(Solves.teamid)

    awards = db.session.query(
        Awards.teamid.label('teamid'),
        db.func.sum(Awards.value).label('score'),
        db.func.max(Awards.id).label('id'),
        db.func.max(Awards.date).label('date')
    )\
        .filter(Awards.value != 0)\
        .group_by(Awards.teamid)

    """
    Filter out solves and awards that are before a specific time point.
    """
    freeze = utils.get_config('freeze')
    if not admin and freeze:
        scores = scores.filter(Solves.date < utils.unix_time_to_utc(freeze))
        awards = awards.filter(Awards.date < utils.unix_time_to_utc(freeze))

    """
    Combine awards and solves with a union. They should have the same amount of columns
    """
    results = union_all(scores, awards).alias('results')

    """
    Sum each of the results by the team id to get their score.
    """
    sumscores = db.session.query(
        results.columns.teamid,
        db.func.sum(results.columns.score).label('score'),
        db.func.max(results.columns.id).label('id'),
        db.func.max(results.columns.date).label('date')
    ).group_by(results.columns.teamid)\
        .subquery()

    """
    Admins can see scores for all users but the public cannot see banned users.

    Filters out banned users.
    Properly resolves value ties by ID.

    Different databases treat time precision differently so resolve by the row ID instead.
    """
    if admin:
        standings_query = db.session.query(
            Teams.id.label('teamid'),
            Teams.name.label('name'),
            Teams.banned, sumscores.columns.score
        )\
            .join(sumscores, Teams.id == sumscores.columns.teamid) \
            .order_by(sumscores.columns.score.desc(), sumscores.columns.id)
    else:
        standings_query = db.session.query(
            Teams.id.label('teamid'),
            Teams.name.label('name'),
            sumscores.columns.score
        )\
            .join(sumscores, Teams.id == sumscores.columns.teamid) \
            .filter(Teams.banned == False) \
            .order_by(sumscores.columns.score.desc(), sumscores.columns.id)

    """
    Only select a certain amount of users if asked.
    """
    if count is None:
        standings = standings_query.all()
    else:
        standings = standings_query.limit(count).all()
    db.session.close()

    return standings

def topteams_endpoint(count):
    json = {'places': {}}
    if utils.get_config('view_scoreboard_if_authed') and not utils.authed():
        return redirect(url_for('auth.login', next=request.path))
    if utils.hide_scores():
        return jsonify(json)

    if count > 20 or count < 0:
        count = 10

    standings = get_standings_monkey_patch(count=count)

    team_ids = [team.teamid for team in standings]

    solves = Solves.query.filter(Solves.teamid.in_(team_ids))
    awards = Awards.query.filter(Awards.teamid.in_(team_ids))

    freeze = utils.get_config('freeze')

    if freeze:
        solves = solves.filter(Solves.date < utils.unix_time_to_utc(freeze))
        awards = awards.filter(Awards.date < utils.unix_time_to_utc(freeze))

    solves = solves.all()
    awards = awards.all()
    time_decay_solves = TimeDecaySolves.query.filter(Solves.teamid.in_(team_ids)).all()

    for i, team in enumerate(team_ids):
        json['places'][i + 1] = {
            'id': standings[i].teamid,
            'name': standings[i].name,
            'solves': []
        }
        for solve in solves:
            if solve.teamid == team:
                score = 0
                for t in time_decay_solves:
                    if t.chalid == solve.chalid and t.teamid == solve.teamid:
                        score = t.decayed_value

                json['places'][i + 1]['solves'].append({
                    'chal': solve.chalid,
                    'team': solve.teamid,
                    'value': score,
                    'time': utils.unix_time(solve.date)
                })
        for award in awards:
            if award.teamid == team:
                json['places'][i + 1]['solves'].append({
                    'chal': None,
                    'team': award.teamid,
                    'value': award.value,
                    'time': utils.unix_time(award.date)
                })
        json['places'][i + 1]['solves'] = sorted(json['places'][i + 1]['solves'], key=lambda k: k['time'])

    return jsonify(json)

def scoreboard_view_endpoint():
    if utils.get_config('view_scoreboard_if_authed') and not utils.authed():
        return redirect(url_for('auth.login', next=request.path))
    if utils.hide_scores():
        return render_template('scoreboard.html', errors=['Scores are currently hidden'])
    standings = get_standings_monkey_patch()
    return render_template('scoreboard.html', teams=standings, score_frozen=utils.is_scoreboard_frozen())

def scores_endpoint():
    json = {'standings': []}
    if utils.get_config('view_scoreboard_if_authed') and not utils.authed():
        return redirect(url_for('auth.login', next=request.path))
    if utils.hide_scores():
        return jsonify(json)

    standings = get_standings_monkey_patch()

    for i, x in enumerate(standings):
        json['standings'].append({'pos': i + 1, 'id': x.teamid, 'team': x.name, 'score': int(x.score)})
    return jsonify(json)

def load(app):
    app.db.create_all()
    CHALLENGE_CLASSES['time-decay'] = TimeDecayChallenge
    register_plugin_assets_directory(app, base_path='/plugins/ctfd-time-decay-plugin/assets/')

    # Monkey patching...
    Teams.score = time_decay_score
    #app.view_functions['challenges.solves_private'] = solves_private_endpoint
    app.view_functions['challenges.solves_public'] = solves_public_endpoint
    app.view_functions['views.team'] = team_endpoint
    app.view_functions['challenges.who_solved'] = who_solved_endpoint
    app.view_functions['scoreboard.topteams'] = topteams_endpoint
    app.view_functions['scoreboard.scoreboard_view'] = scoreboard_view_endpoint
    app.view_functions['scoreboard.scores'] = scores_endpoint
