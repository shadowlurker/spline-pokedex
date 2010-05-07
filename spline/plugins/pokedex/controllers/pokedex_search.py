# encoding: utf8
from __future__ import absolute_import, division

import logging
import re
from string import Template

from wtforms import Form, ValidationError, fields, widgets
from wtforms.ext.sqlalchemy.fields import QuerySelectField

import pokedex.db.tables as tables
from pylons import config, request, response, session, tmpl_context as c, url
from pylons.controllers.util import abort, redirect_to
from sqlalchemy.orm import aliased, eagerload, eagerload_all
from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy.sql import func, and_, not_, or_
from sqlalchemy.sql.operators import asc_op

from spline.lib import helpers as h
from spline.lib.base import BaseController, render
from spline.lib.forms import DuplicateField, MultiCheckboxField, QueryCheckboxSelectMultipleField, QueryTextField

from spline.plugins.pokedex import helpers as pokedex_helpers
from spline.plugins.pokedex.db import pokedex_session
from spline.plugins.pokedex.forms import PokedexLookupField, RangeTextField
from spline.plugins.pokedex.magnitude import parse_size

log = logging.getLogger(__name__)

# XXX probably needs to live elsewhere
default_pokemon_table_columns = [
    'icon',
    'name',
    'type',
    'ability',
    'gender',
    'egg_group',
    'stat_hp',
    'stat_attack',
    'stat_defense',
    'stat_special_attack',
    'stat_special_defense',
    'stat_speed',
    'stat_total',
]

def ilike(column, string):
    string = string.lower()

    # If there are no wildcards, assume it's a partial match
    if '*' not in string and '?' not in string:
        string = u"*{0}*".format(string)

    # LIKE wildcards should be escaped: % -> ^%, _ -> ^_, ^ -> ^^
    # Our wildcards should be changed: * -> %, ? -> _
    # And all at once.
    translations = {
        '%': u'^%',     '_': u'^_',     '^': u'^^',
        '*': u'%',      '?': u'_',
    }
    string = re.sub(ur'([%_*?^])',
                    lambda match: translations[match.group(0)],
                    string)

    return func.lower(column).like(string, escape='^')


def in_pokedex_label(pokedex):
    """[ IV ] Sinnoh"""

    return """{gen_icon} {name}""".format(
        gen_icon=pokedex_helpers.generation_icon(pokedex.region.generation),
        name=pokedex.name,
    )

class PokemonSearchForm(Form):
    # Defaults are set to match what the client will actually send if the field
    # is left blank
    shorten = fields.HiddenField(default=u'')

    id = RangeTextField('National ID', inflator=int)

    # Core stuff
    name = fields.TextField('Name', default=u'')
    ability = PokedexLookupField('Ability', valid_type='ability', allow_blank=True)
    held_item = PokedexLookupField('Held item', valid_type='item', allow_blank=True)
    growth_rate = QuerySelectField('Growth rate',
        query_factory=lambda: pokedex_session.query(tables.GrowthRate),
        get_pk=lambda _: _.max_experience,
        get_label=lambda _: """{0} ({1:n} EXP)""".format(_.name, _.max_experience),
        allow_blank=True,
    )

    # Type
    type_operator = fields.SelectField(
        choices=[
            (u'any',   'at least one of these types'),
            (u'exact', 'exactly these types'),
            (u'only',  'only these types'),
        ],
        default=u'any',
    )
    type = QueryCheckboxSelectMultipleField(
        'Type',
        query_factory=lambda: pokedex_session.query(tables.Type),
        get_label=lambda _: _.name,
        get_pk=lambda table: table.name,
        allow_blank=True,
    )

    # Breeding
    gender_rate_operator = fields.SelectField(
        choices=[
            (u'more_equal', u'at least'),
            (u'equal',      u'exactly'),
            (u'less_equal', u'at most'),
        ],
        default=u'equal',
    )
    gender_rate = fields.SelectField('Gender distribution',
        choices=[
            (u'',   u''),
            (u'0',  u'Never female'),
            (u'1',  u'1/8 female'),
            (u'2',  u'1/4 female'),
            (u'3',  u'3/8 female'),
            (u'4',  u'1/2 female'),
            (u'5',  u'5/8 female'),
            (u'6',  u'3/4 female'),
            (u'7',  u'7/8 female'),
            (u'8',  u'Always female'),
            (u'-1', u'Genderless'),
        ],
        default=u'',
    )

    egg_group_operator = fields.SelectField(
        choices=[ ('any', 'any of'), ('all', 'all of') ],
        default='all',
    )
    egg_group = DuplicateField(
        QuerySelectField(
            'Egg group',
            query_factory=lambda: pokedex_session.query(tables.EggGroup),
            get_label=lambda _: _.name,
            allow_blank=True,
        ),
        min_entries=2,
        max_entries=2,
    )

    # Evolution
    evolution_stage = MultiCheckboxField('Stage',
        choices=[
            (u'baby',   u'baby'),
            (u'basic',  u'basic'),
            (u'stage1', u'stage 1'),
            (u'stage2', u'stage 2'),
        ],
    )
    evolution_position = MultiCheckboxField('Position',
        choices=[
            (u'first',  u'First evolution'),
            (u'middle', u'Middle evolution'),
            (u'last',   u'Final evolution'),
            (u'only',   u'Only evolution'),
        ],
    )
    evolution_special = MultiCheckboxField('Special',
        choices=[
            (u'branching', u'Branching evolution (e.g., Tyrogue)'),
            (u'branched',  u'Branched evolution (e.g., Shedinja)'),
        ],
    )

    # Generation
    introduced_in = QueryCheckboxSelectMultipleField(
        'Introduced in',
        query_factory=lambda: pokedex_session.query(tables.Generation),
        get_label=lambda _: pokedex_helpers.generation_icon(_),
        get_pk=lambda table: table.id,
        allow_blank=True,
    )
    in_pokedex = QueryCheckboxSelectMultipleField(
        u'In regional Pokédex',
        query_factory=lambda: pokedex_session.query(tables.Pokedex) \
                                  .join(tables.Generation) \
                                  .options(eagerload_all('region.generation')),
        get_label=in_pokedex_label,
        get_pk=lambda table: table.id,
        allow_blank=True,
    )

    # Moves
    move = DuplicateField(
        QueryTextField(
            u'',
            query_factory=
                lambda value: pokedex_session.query(tables.Move)
                    .filter( func.lower(tables.Move.name) == value.lower() ),
            get_label=lambda _: _.name,
            allow_blank=True,
        ),
        min_entries=4,
        max_entries=4,
    )
    # XXX tests claim this will also do "similar moves", but I don't know what
    # that means.  same categories..?
    move_fuzz = fields.SelectField('Accept',
        choices=[
            (u'exact-move', 'Only these moves'),
            (u'same-effect', 'Any moves with the same effect'),
        ],
        default=u'exact-move',
    )
    move_method = QueryCheckboxSelectMultipleField(
        'Learned by',
        query_factory=lambda: pokedex_session.query(tables.PokemonMoveMethod)
            # XXX move methods need to identify themselves as "common"
            .filter(tables.PokemonMoveMethod.id <= 4),
        get_label=lambda row: row.name,
        get_pk=lambda table: table.name.lower().replace(' ', '-'),
        allow_blank=True,
    )
    move_version_group = QueryCheckboxSelectMultipleField(
        'Versions',
        query_factory=lambda: pokedex_session.query(tables.VersionGroup) \
                                             .options(eagerload('versions')),
        get_label=lambda row: pokedex_helpers.version_icons(*row.versions),
        get_pk=lambda table: table.id,
        allow_blank=True,
    )

    # Numbers
    # Effort and stats are pulled from the database, so those fields are added
    # dynamically
    steps_to_hatch = RangeTextField('Steps to hatch', inflator=int)
    base_experience = RangeTextField('Base EXP', inflator=int)
    capture_rate = RangeTextField('Capture rate', inflator=int)
    base_happiness = RangeTextField('Base happiness', inflator=int)

    height = RangeTextField('Height', inflator=lambda _: parse_size(_, 'height'))
    weight = RangeTextField('Weight', inflator=lambda _: parse_size(_, 'weight'))

    # Flavor
    species = fields.TextField('Species', default=u'')
    color = QuerySelectField('Color',
        query_factory=lambda: pokedex_session.query(tables.PokemonColor),
        get_label=lambda _: _.name,
        allow_blank=True,
        get_pk=lambda table: table.name,
    )
    habitat = QuerySelectField('Habitat',
        query_factory=lambda: pokedex_session.query(tables.PokemonHabitat),
        get_label=lambda _: _.name,
        allow_blank=True,
        get_pk=lambda table: table.name,
    )
    shape = QuerySelectField('Shape',
        query_factory=lambda: pokedex_session.query(tables.PokemonShape)
            .order_by(tables.PokemonShape.name.asc()),
        get_label=lambda _: _.name,
        get_pk=lambda _: _.name.lower(),
        allow_blank=True,
    )


    # Order and display
    # XXX mention fallback sort?  have a sort2?
    sort = fields.SelectField('Sort by',
        choices=[
            ('id', 'National dex number'),
            ('evolution-chain', 'Evolution family'),
            ('name', 'Name'),
            ('type', 'Type'),
            ('steps-to-hatch', 'Steps to hatch'),
            ('base-experience', 'Base EXP'),
            ('capture-rate', 'Capture rate'),
            ('base-happiness', 'Base happiness'),
            ('height', 'Height'),
            ('weight', 'Weight'),
            ('gender', 'Gender rate'),
            ('species', 'Species'),
            ('color', 'Color'),
            ('habitat', 'Habitat'),
            ('shape', 'Shape'),
            ('stat-hp', 'HP'),
            ('stat-attack', 'Attack'),
            ('stat-defense', 'Defense'),
            ('stat-special-attack', 'Special Attack'),
            ('stat-special-defense', 'Special Defense'),
            ('stat-speed', 'Speed'),
            ('stat-total', 'Stat total'),
        ],
        default='name',
    )
    sort_backwards = fields.BooleanField('Sort backwards')

    display = fields.SelectField('Display',
        choices=[
            ('standard-table', 'Standard table'),
            ('smart-table', 'Smart table'),
            ('custom-table', 'Custom table'),
            ('simple-list', 'Simple list'),
            ('custom-list', 'Custom list'),
            ('icons', 'Icons'),
            ('sprites', 'Sprites'),
        ],
        default='smart-table',
    )

    column = MultiCheckboxField(
        'Custom table columns',
        choices=[
            ('id', 'National ID'),
            ('icon', 'Icon'),
            ('name', 'Name'),
            ('type', 'Types'),
            ('growth_rate', 'EXP to level 100'),
            ('ability', 'Abilities'),
            ('gender', 'Gender rate'),
            ('egg_group', 'Egg groups'),

            ('height', 'Height'),
            ('height_metric', 'Height (in metric)'),
            ('weight', 'Weight'),
            ('weight_metric', 'Weight (in metric)'),
            ('species', 'Species'),
            ('color', 'Color'),
            ('habitat', 'Habitat'),
            ('shape', 'Shape'),
            ('steps_to_hatch', 'Steps to hatch'),
            ('base_experience', 'Base EXP'),
            ('capture_rate', 'Capture rate'),
            ('base_happiness', 'Base happiness'),

            ('stat_hp', 'HP'),
            ('stat_attack', 'Attack'),
            ('stat_defense', 'Defense'),
            ('stat_special_attack', 'Special Attack'),
            ('stat_special_defense', 'Special Defense'),
            ('stat_speed', 'Speed'),
            ('stat_total', 'Stat total'),
            ('effort', 'Effort given'),
        ],
        default=default_pokemon_table_columns,
    )
    format = fields.TextField('Custom list format', default=u'$icon $name')



    def __init__(self, formdata=None, *args, **kwargs):
        """Saves a copy of the passed form data, with default values removed,
        in the `formdata` property.
        """

        super(PokemonSearchForm, self).__init__(formdata, *args, **kwargs)

        # Two factoids we need to remember about this form: was it submitted at
        # all, and is it valid?
        self.is_valid = None
        self.was_submitted = None
        self.needs_shortening = bool(formdata.get('shorten', False))
        self.cleansed_data = dict()

        # Need to make a copy and delete items, rather than creating a new
        # dict, because formdata is some variant of a multi-dict
        if self.needs_shortening and formdata:
            self.was_submitted = True
            self.cleansed_data = formdata.copy()
            del self.cleansed_data['shorten']

            for name, field in self._fields.iteritems():
                # Shorten: nuke anything that's a default
                if field.data == field.default and name in self.cleansed_data:
                    del self.cleansed_data[name]

        elif not self.needs_shortening:
            self.was_submitted = bool(formdata)

            # Unshortening.  Fields that are missing entirely from the form
            # data need to be FILLED IN with their defaults.
            # Note that this will cheerfully fill in a multi-select field where
            # nothing was selected; it's assumed that a multi-select field with
            # a default makes no sense with nothing selected
            for name, field in self._fields.iteritems():
                if field.default and name not in formdata:
                    field.data = field.default

    def validate(self):
        # XXX this works around a wtforms bug; QueryMultiSelectField (or
        # whatever it's called) lazily checks or errors when field.data is
        # accessed, but that's not likely to happen before validating!  Ping
        # all the field data
        for name, field in self._fields.iteritems():
            field.data

        self.is_valid = super(PokemonSearchForm, self).validate()

        return self.is_valid


class PokedexSearchController(BaseController):

    def pokemon_search(self):
        class F(PokemonSearchForm):
            pass

        # Add stat-based fields dynamically
        c.stat_fields = []
        for stat in pokedex_session.query(tables.Stat) \
                                   .order_by(tables.Stat.id):
            field_name = stat.name.lower().replace(u' ', u'_')

            stat_field = RangeTextField(stat.name, inflator=int)
            effort_field = RangeTextField(stat.name, inflator=int)

            c.stat_fields.append((stat.id, field_name))

            setattr(F, 'stat_' + field_name, stat_field)
            setattr(F, 'effort_' + field_name, effort_field)


        ### Parse form, etc etc
        c.form = F(request.params)
        c.form.validate()

        # Rendering needs to know which version groups go with which
        # generations for the move-version-group list
        c.generations = pokedex_session.query(tables.Generation) \
            .order_by(tables.Generation.id.asc())

        # If this is the first time the form was submitted, redirect to a URL
        # with only non-default values
        if c.form.is_valid and c.form.was_submitted and c.form.needs_shortening:
            redirect_to(url.current(**c.form.cleansed_data.mixed()))

        if not c.form.was_submitted or not c.form.is_valid:
            # Either blank, or errortastic.  Skip the logic and just send the
            # form back
            return render('/pokedex/search/pokemon.mako')


        ### Do the searching!
        me = tables.Pokemon
        query = pokedex_session.query(me)

        # Sorting and filtering by stat both need to join to the stat table for
        # the specific stat in question.  Keep track of these joins to avoid
        # doing them multiple times
        stat_aliases = {}
        def join_to_stat(stat):
            # stat can be an id, object, or name
            if isinstance(stat, basestring):
                stat = pokedex_session.query(tables.Stat).filter_by(name=stat) \
                                      .one()
            elif isinstance(stat, int):
                stat = pokedex_session.query(tables.Stat).get(stat)

            if stat not in stat_aliases:
                stat_alias = aliased(tables.PokemonStat)
                new_query = query.join(stat_alias)
                new_query = new_query.filter(stat_alias.stat_id == stat.id)
                stat_aliases[stat] = stat_alias
            else:
                new_query = query

            return new_query, stat_aliases[stat]

        # Same applies to a couple other tables...
        joins = []
        def join_once(relation):
            if relation in joins:
                return query

            new_query = query.join(relation)
            joins.append(relation)
            return new_query

        # ID
        if c.form.id.data:
            # Have to handle forms and not-forms differently
            query = query.filter(
                or_(
                    and_(
                        c.form.id.data(me.id),
                        me.forme_base_pokemon_id == None,
                    ),
                    c.form.id.data(me.forme_base_pokemon_id),
                )
            )

        # Name
        if c.form.name.data:
            name = c.form.name.data.strip().lower()

            if ' ' in name:
                # Hmm.  If there's a space, it might be a form name
                form_name, name_sans_form = name.split(' ', 1)
                query = query.filter(
                    or_(
                        # Either it was a form name...
                        and_(
                            ilike( me.forme_name, form_name ),
                            ilike( me.name, name_sans_form ),
                        ),
                        # ...or not.
                        ilike( me.name, name ),
                    )
                )
            else:
                # Busines as usual
                query = query.filter( ilike(me.name, name) )

        # Ability
        if c.form.ability.data:
            query = query.filter( me.abilities.any(
                                    tables.Ability.id == c.form.ability.data.id
                                  )
                                )

        # Held item
        if c.form.held_item.data:
            item_subquery = pokedex_session.query(
                    tables.PokemonItem.pokemon_id
                ) \
                .filter_by(item_id=c.form.held_item.data.id) \
                .subquery()

            query = query.join((item_subquery,
                me.id == item_subquery.c.pokemon_id))

        # Growth rate
        if c.form.growth_rate.data:
            query = join_once(me.evolution_chain) \
                .filter(tables.EvolutionChain.growth_rate == c.form.growth_rate.data)

        # Type
        if c.form.type.data:
            type_ids = [_.id for _ in c.form.type.data]

            if c.form.type_operator.data == u'any':
                # Well, this is easy; be lazy and use EXISTS
                query = query.filter(
                    me.types.any( tables.Type.id.in_(type_ids) )
                )

            elif c.form.type_operator.data == u'only':
                # None of this Pokémon's types can be not selected.  Right.
                query = query.filter(
                    ~ me.types.any( ~ tables.Type.id.in_(type_ids) )
                )

            elif c.form.type_operator.data == u'exact':
                # This one is interesting, and not quite so easy to express
                # with set operations.  It's like 'only', except every selected
                # type also must be one of the Pokémon's types.  Thus we
                # combine the above two approaches:
                query = query.filter(
                    ~ me.types.any( ~ tables.Type.id.in_(type_ids) )
                )

                for type_id in type_ids:
                    query = query.filter(
                        me.types.any( tables.Type.id == type_id )
                    )

        # Gender distribution
        if c.form.gender_rate.data:
            gender_rate = int(c.form.gender_rate.data)
            gender_rate_op = c.form.gender_rate_operator.data

            # Genderless ignores the operator
            if gender_rate == -1 or gender_rate_op == 'equal':
                clause = me.gender_rate == gender_rate
            elif gender_rate_op == 'less_equal':
                clause = me.gender_rate <= gender_rate
            elif gender_rate_op == 'more_equal':
                clause = me.gender_rate >= gender_rate

            if gender_rate != -1:
                # No amount of math should make "<= 1/4 female" include
                # genderless
                clause = and_(clause, me.gender_rate != -1)

            query = query.filter(clause)

        # Egg groups
        if any(c.form.egg_group.data):
            clauses = []
            for egg_group in c.form.egg_group.data:
                if not egg_group:
                    continue
                subclause = me.egg_groups.any(
                    tables.EggGroup.id == egg_group.id
                )
                clauses.append(subclause)

            if c.form.egg_group_operator.data == 'any':
                clause = or_(*clauses)
            elif c.form.egg_group_operator.data == 'all':
                clause = and_(*clauses)

            query = query.filter(clause)

        # Evolution stuff
        # Try to limit our joins without duplicating too much code
        # Stage and position generally need to know parents:
        if c.form.evolution_stage.data or c.form.evolution_position.data:
            # NOTE: This makes the assumption that evolution chains are never
            # more than three Pokémon long.  So far, this is pretty safe, as in
            # 10+ years no Pokémon has ever been able to evolve more than
            # twice.  If this changes, then either this query will need a
            # greatgrandparent, or (likely) the table structure will change
            parent_pokemon = aliased(tables.Pokemon)
            grandparent_pokemon = aliased(tables.Pokemon)

            # Make it an outer join; could be a search for e.g. 'baby', which
            # definitely doesn't want inner
            query = query.outerjoin((
                parent_pokemon,
                me.evolution_parent_pokemon_id == parent_pokemon.id
            )) \
            .outerjoin((
                grandparent_pokemon,
                parent_pokemon.evolution_parent_pokemon_id == grandparent_pokemon.id
            ))

        # ...whereas position and special tend to need children
        if c.form.evolution_position.data or c.form.evolution_special.data:
            child_pokemon = aliased(tables.Pokemon)
            child_subquery = pokedex_session.query(
                    child_pokemon.evolution_parent_pokemon_id.label('parent_id'),
                    func.count('*').label('child_count'),
                ) \
                .group_by(child_pokemon.evolution_parent_pokemon_id) \
                .subquery()

            query = query.outerjoin((
                child_subquery,
                me.id == child_subquery.c.parent_id
            ))

        if c.form.evolution_stage.data:
            # Collect clauses for the requested stages and add to the query
            clauses = []
            if u'baby' in c.form.evolution_stage.data:
                # Baby form: is_baby.  Cool, easy.
                clauses.append( me.is_baby == True )

            if u'basic' in c.form.evolution_stage.data:
                # Basic: this is not a baby.  Either there's no parent, or
                # parent is a baby
                clauses.append(
                    and_(
                        me.is_baby == False,
                        or_(
                            parent_pokemon.id == None,
                            parent_pokemon.is_baby == True,
                        )
                    )
                )

            if u'stage1' in c.form.evolution_stage.data:
                # Stage 1: parent exists and is not a baby.  Grandparent either
                # doesn't exist or is a baby
                clauses.append(
                    and_(
                        parent_pokemon.id != None,
                        parent_pokemon.is_baby == False,
                        or_(
                            grandparent_pokemon.id == None,
                            grandparent_pokemon.is_baby == True,
                        ),
                    )
                )

            if u'stage2' in c.form.evolution_stage.data:
                # Stage 2: grandparent exists and is not a baby
                clauses.append(
                    and_(
                        grandparent_pokemon.id != None,
                        grandparent_pokemon.is_baby == False,
                    )
                )

            query = query.filter(or_(*clauses))

        if c.form.evolution_position.data:
            # Same story
            clauses = []

            if u'first' in c.form.evolution_position.data:
                # No parent
                clauses.append( parent_pokemon.id == None )

            if u'middle' in c.form.evolution_position.data:
                # Has a parent AND a child
                clauses.append(
                    and_(
                        parent_pokemon.id != None,
                        child_subquery.c.child_count != None,
                    )
                )

            if u'last' in c.form.evolution_position.data:
                # No children
                clauses.append( child_subquery.c.child_count == None )

            if u'only' in c.form.evolution_position.data:
                # No parent; children
                clauses.append(
                    and_(
                        parent_pokemon.id == None,
                        child_subquery.c.child_count == None,
                    )
                )

            query = query.filter(or_(*clauses))

        if c.form.evolution_special.data:
            clauses = []

            if u'branching' in c.form.evolution_special.data:
                # Branching means: multiple children.  Easy!
                clauses.append( child_subquery.c.child_count > 1 )

            if u'branched' in c.form.evolution_special.data:
                # Need to join to..  siblings.  Ugh.
                sibling_pokemon = aliased(tables.Pokemon)
                sibling_subquery = pokedex_session.query(
                    sibling_pokemon.evolution_parent_pokemon_id.label('parent_id'),
                    func.count('*').label('sibling_count'),
                ) \
                    .group_by(sibling_pokemon.evolution_parent_pokemon_id) \
                    .subquery()

                query = query.outerjoin((
                    sibling_subquery,
                    me.evolution_parent_pokemon_id
                        == sibling_subquery.c.parent_id
                ))

                clauses.append( sibling_subquery.c.sibling_count > 1 )

            query = query.filter(or_(*clauses))

        # Generation
        if c.form.introduced_in.data:
            query = query.filter(
                me.generation_id.in_(_.id for _ in c.form.introduced_in.data)
            )

        if c.form.in_pokedex.data:
            # Need a subquery that finds all the Pokémon in all the selected
            # Pokédexes
            pokedex_numbers = aliased(tables.PokemonDexNumber)
            pokedex_subquery = pokedex_session.query(
                pokedex_numbers.pokemon_id,
            ) \
                .filter(pokedex_numbers.pokedex_id.in_(
                    _.id for _ in c.form.in_pokedex.data
                )) \
                .group_by(pokedex_numbers.pokemon_id) \
                .subquery()

            query = query.join((
                pokedex_subquery,
                me.id == pokedex_subquery.c.pokemon_id,
            ))

        # Moves
        if c.form.move.data:
            # To avoid stupid group-by-having-count tricks, each move needs to
            # join to a separate subquery of Pokémon that learn the given move
            # under the given conditions.
            move_version_groups = [_.id for _ in c.form.move_version_group.data]
            move_methods = [_.id for _ in c.form.move_method.data]

            for move in c.form.move.data:
                # Apply fuzzing
                if c.form.move_fuzz.data == 'same-effect':
                    move_effect_query = pokedex_session.query(tables.Move) \
                        .filter_by(effect_id=move.effect_id)
                    move_ids = [id for (id,) in
                        move_effect_query.values(tables.Move.id)]
                else:
                    move_ids = [move.id]

                move_alias = aliased(tables.PokemonMove)
                move_subquery = pokedex_session.query(move_alias.pokemon_id) \
                    .filter(move_alias.move_id.in_(move_ids))

                if move_methods:
                    move_subquery = move_subquery.filter(
                        move_alias.pokemon_move_method_id.in_(move_methods))
                if move_version_groups:
                    move_subquery = move_subquery.filter(
                        move_alias.version_group_id.in_(move_version_groups))

                move_subquery = move_subquery.subquery()  # ok, dumb, but...

                query = query.join((
                    move_subquery,
                    move_subquery.c.pokemon_id == me.id
                ))

                # The INNER JOIN does the filtering automatically, so nothing
                # else to do


        # Numbers
        for stat_id, field_name in c.stat_fields:
            stat_field = c.form['stat_' + field_name]
            effort_field = c.form['effort_' + field_name]

            if stat_field.data or effort_field.data:
                query, stat_alias = join_to_stat(stat_id)

                if stat_field.data:
                    query = query.filter(stat_field.data(stat_alias.base_stat))

                if effort_field.data:
                    query = query.filter(effort_field.data(stat_alias.effort))

        if c.form.steps_to_hatch.data:
            query = join_once(me.evolution_chain) \
                .filter(c.form.steps_to_hatch.data(
                    tables.EvolutionChain.steps_to_hatch))

        if c.form.base_experience.data:
            query = query.filter(c.form.base_experience.data(me.base_experience))

        if c.form.capture_rate.data:
            query = query.filter(c.form.capture_rate.data(me.capture_rate))

        if c.form.base_happiness.data:
            query = query.filter(c.form.base_happiness.data(me.base_happiness))

        if c.form.height.data:
            query = query.filter(c.form.height.data(me.height))

        if c.form.weight.data:
            query = query.filter(c.form.weight.data(me.weight))

        # Species string
        if c.form.species.data:
            query = query.filter(ilike(me.species, c.form.species.data))

        # Color
        if c.form.color.data:
            query = query.filter( me.color_id == c.form.color.data.id )

        # Habitat
        if c.form.habitat.data:
            query = query.filter( me.habitat_id == c.form.habitat.data.id )

        # Shape
        if c.form.shape.data:
            query = query.filter( me.pokemon_shape_id == c.form.shape.data.id )


        ### Display
        c.display_mode = c.form.display.data
        c.display_columns = []
        c.original_results = None  # evolution chain thing

        if c.display_mode == 'standard-table':
            # Just do a "custom" table with a manual set of columns that happen
            # to be the standard columns...
            c.display_mode = 'custom-table'
            c.display_columns = default_pokemon_table_columns

        elif c.display_mode == 'smart-table':
            # Based on the standard table, but a little more clever.  For
            # example: searching by moves will show how the move is learned by
            # each resulting Pokémon.
            # TODO actually do that.
            c.display_mode = 'custom-table'
            c.display_columns = default_pokemon_table_columns

        elif c.display_mode == 'custom-table':
            # User can pick whatever columns, in any order.  Woo!
            c.display_columns = c.form.column.data
            if not c.display_columns:
                # Hmm.  Show name, at least.
                c.display_columns = ['name']

        elif c.display_mode == 'simple-list':
            # This is a custom list with a fixed format string
            c.display_mode = 'custom-list'
            c.display_template = Template(u'$icon $name')

        elif c.display_mode == 'custom-list':
            # Use whatever they asked for; it'll get pumped through
            # safe_substitute anyway.  This uses apply_pokemon_template from
            # the pokedex helpers
            c.display_template = Template(
                h.escape(c.form.format.data)
            )

        else:
            # icons and sprites don't need any special behavior
            pass

        # "Name" is the field that actually links to the page.  If it's
        # missing, add a little link column
        if c.display_mode == 'custom-table' and 'name' not in c.display_columns:
            c.display_columns.append('link')

        ### Sorting
        # nb: the below sort ascending for words (a->z) and descending for
        # numbers (9->1), because that's how it should be, okay
        # Default fallback sort is by name, then by id (in case of form)
        sort_clauses = [ me.name.asc(), me.id.asc() ]
        if c.form.sort.data == 'id':
            sort_clauses.insert(0,
                func.coalesce(me.forme_base_pokemon_id, me.id).asc()
            )

        elif c.form.sort.data == 'evolution-chain':
            # This one is very special!  It affects sorting, but if the display
            # is a table, sorting by chain will also show other Pokémon from
            # each family, even if they don't match the search criteria.
            # E.g., a search that produces Bulbasaur will display Bulbasaur,
            # followed by Ivysaur and Venusaur dimmed.
            # XXX doing this for lists would be nice, too, but would sort of
            # break copy/paste, which is what lists are designed for

            # DO NOT allow sorting backwards!  It breaks the template's
            # indenting magic.  XXX fix me!
            c.form.sort_backwards.data = False

            # Grab the results first; needed for sorting even if the query is
            # otherwise left alone, boo
            pokemon_ids = {}
            evolution_chain_ids = set()
            for id, chain_id in query.values(me.id, me.evolution_chain_id):
                evolution_chain_ids.add(chain_id)
                pokemon_ids[id] = None

            # Rebuild the query
            if c.display_mode in ('custom-table',):
                query = pokedex_session.query(me).filter(
                    me.evolution_chain_id.in_( list(evolution_chain_ids) )
                )
            else:
                query = pokedex_session.query(me) \
                    .filter(me.id.in_(pokemon_ids.keys()))

            # Let the template know which Pokémon are actually in the original
            # result set
            c.original_results = pokemon_ids

            # Pokémon should be sorted by the id number of the first form of
            # their chain to actually appear in the results.  This is wonky,
            # but makes sure that fake results don't affect sorting
            chain_sorting_alias = aliased(tables.Pokemon)
            chain_sorting_subquery = pokedex_session.query(
                    chain_sorting_alias.evolution_chain_id,
                    func.min(chain_sorting_alias.id).label('chain_position')
                ) \
                .filter(chain_sorting_alias.id.in_(pokemon_ids)) \
                .group_by(chain_sorting_alias.evolution_chain_id) \
                .subquery()

            query = query.join((
                chain_sorting_subquery,
                chain_sorting_subquery.c.evolution_chain_id
                    == me.evolution_chain_id
            ))

            sort_clauses = [
                    chain_sorting_subquery.c.chain_position,
                    me.is_baby.desc(),
                    me.id.asc(),
                ] + sort_clauses

        elif c.form.sort.data == 'name':
            # Name is fallback, so don't do anything
            pass

        elif c.form.sort.data == 'type':
            # Sort by type1, then type2.  Unfortunately, need to left-join
            # independently for each type to make this work right
            type_sort_clauses = []
            for type_slot in [1, 2]:
                pokemon_type_alias = aliased(tables.PokemonType)
                type_alias = aliased(tables.Type)

                query = query \
                    .outerjoin((pokemon_type_alias,
                        and_(pokemon_type_alias.pokemon_id == me.id,
                             pokemon_type_alias.slot == type_slot))) \
                    .outerjoin((type_alias,
                        pokemon_type_alias.type_id == type_alias.id))

                # Single-type should come first; i.e., sorting by type2 asc
                # means NULL should come first.  This isn't the default in
                # postgres (and elsewhere?), so do it explicitly
                if type_slot == 2:
                    # Booleans sort by false, true -- so this should be desc to
                    # put NULL first
                    type_sort_clauses.append((type_alias.id == None).desc())

                type_sort_clauses.append(type_alias.name.asc())

            sort_clauses = type_sort_clauses + sort_clauses

        elif c.form.sort.data == 'height':
            sort_clauses.insert(0, me.height.desc())

        elif c.form.sort.data == 'weight':
            sort_clauses.insert(0, me.weight.desc())

        elif c.form.sort.data == 'gender':
            sort_clauses.insert(0, me.gender_rate.asc())

        elif c.form.sort.data == 'species':
            sort_clauses.insert(0, me.species.asc())

        elif c.form.sort.data == 'color':
            query = join_once(me.pokemon_color)
            sort_clauses.insert(0, tables.PokemonColor.name.asc())

        elif c.form.sort.data == 'habitat':
            query = query.outerjoin(tables.PokemonHabitat)
            sort_clauses.insert(0, tables.PokemonHabitat.name.asc())

        elif c.form.sort.data == 'steps-to-hatch':
            query = join_once(me.evolution_chain)
            sort_clauses.insert(0, tables.EvolutionChain.steps_to_hatch.asc())

        elif c.form.sort.data == 'base-experience':
            sort_clauses.insert(0, me.base_experience.desc())

        elif c.form.sort.data == 'capture-rate':
            sort_clauses.insert(0, me.capture_rate.desc())

        elif c.form.sort.data == 'base-happiness':
            sort_clauses.insert(0, me.base_happiness.desc())

        elif c.form.sort.data == 'stat-total':
            # Create a subquery that sums all base stats
            stat_total = aliased(tables.PokemonStat)
            stat_total_subquery = pokedex_session.query(
                    stat_total.pokemon_id,
                    func.sum(stat_total.base_stat).label('stat_total'),
                ) \
                .group_by(stat_total.pokemon_id) \
                .subquery()

            query = query.outerjoin((
                stat_total_subquery,
                me.id == stat_total_subquery.c.pokemon_id
            ))

            sort_clauses.insert(0, stat_total_subquery.c.stat_total.desc())

        elif c.form.sort.data[0:5] == 'stat-':
            # Gross!  stat_special_attack => Special Attack
            stat_name = c.form.sort.data[5:]
            if stat_name == 'hp':
                stat_name = 'HP'
            else:
                stat_name = stat_name.replace('-', ' ').title()

            query, stat_alias = join_to_stat(stat_name)
            sort_clauses.insert(0, stat_alias.base_stat.desc())

        # Reverse sort
        if c.form.sort_backwards.data:
            for i, clause in enumerate(sort_clauses):
                # This is some semi-black SQLA magic...
                if clause.modifier == asc_op:
                    sort_clauses[i] = clause.element.desc()
                else:
                    sort_clauses[i] = clause.element.asc()

        query = query.order_by(*sort_clauses)


        ### Run the query!
        c.results = query.all()
        print query


        ### Eagerloading
        # SQLAlchemy is guaranteed to only have one copy of a particular object
        # around at a time.  So if I run queries with the same results several
        # times, but eagerload something different each time, I'll only have
        # one set of obects with all of the eagerloads present on each.
        # For simplicity, and because all of the conditional eagerloads are
        # has-manies, this code abuses the above property to eagerload
        # everything after-the-fact, based on which table columns are visible.
        # TODO doesn't apply so much to lists at the moment...
        if c.results and c.display_mode == 'custom-table':
            eagerloads = []

            if 'type' in c.display_columns:
                eagerloads.append('types')

            if 'ability' in c.display_columns:
                eagerloads.append('abilities')

            if 'egg_group' in c.display_columns:
                eagerloads.append('egg_groups')

            if any(column[0:5] == 'stat_' for column in c.display_columns) \
                or 'effort' in c.display_columns:

                eagerloads.append('stats.stat')


            ids = [_.id for _ in c.results]
            for relation in eagerloads:
                # Run the query again, selecting only by id this time, but
                # eagerloading some relation
                pokedex_session.query(tables.Pokemon) \
                    .filter(tables.Pokemon.id.in_(ids)) \
                    .options(eagerload_all(relation)) \
                    .all()

        ### Done.
        return render('/pokedex/search/pokemon.mako')
