<%inherit file="/base.mako"/>
<%namespace name="lib" file="lib.mako"/>
<%! from spline.plugins.pokedex import db %>\
<%! import re %>\

<%def name="title()">\
% if c.pokemon.forme_name:
${c.pokemon.forme_name.capitalize()} \
% endif
${c.pokemon.name} — Pokémon #${c.pokemon.national_id}\
</%def>

${lib.pokemon_page_header()}


<h1 id="essentials"><a href="#essentials" class="subtle">Essentials</a></h1>

## Portrait block
<div class="dex-page-portrait">
    <p id="dex-page-name">${c.pokemon.name}</p>
    % if c.pokemon.forme_name:
    <p id="dex-pokemon-forme">${c.pokemon.forme_name.capitalize()} Forme</p>
    % endif
    ${h.pokedex.pokemon_sprite(c.pokemon, prefix='heartgold-soulsilver', id="dex-pokemon-portrait-sprite")}
    <p id="dex-page-types">
        % for type in c.pokemon.types:
        ${h.pokedex.type_link(type)}
        % endfor
    </p>
</div>

<div class="dex-page-beside-portrait">
<h2>Abilities</h2>
<dl>
    % for ability in c.pokemon.abilities:
    <dt>${ability.name}</dt>
    <dd>${ability.effect}</dd>
    % endfor
</dl>

<h2>Damage Taken</h2>
## Boo not using <dl>  :(  But I can't get them to align horizontally with CSS2
## if the icon and value have no common element..
<ul class="dex-page-damage">
    ## always sort ??? last
    % for type, damage_factor in sorted(c.type_efficacies.items(), \
                                        key=lambda x: (x[0].id == 18, x[0].name)):
    <li class="dex-damage-taken-${damage_factor}">
        ${h.pokedex.type_link(type)} ${h.pokedex.type_efficacy_label[damage_factor]}
    </li>
    % endfor
</ul>
</div>

<div class="dex-column-container">
<div class="dex-column">
    <h2>Pokédex Numbers</h2>
<%
    dex_numbers = {} # dex => [number, generation]; generation is None if no generation is to be shown
    to_show = ('National', 'Kanto', 'New', 'Hoenn', 'Sinnoh', 'Johto') # 'New' is GSC Johto dex

    for number in c.pokemon.normal_form.dex_numbers:
        dex_name = number.pokedex.name
        if dex_name in to_show:
            if number.pokedex.id == 6 and 'Sinnoh' in dex_numbers.keys():
                # Prefer D/P Sinnoh dex over Platinum: Pt won't usurp an existing D/P entry, but a D/P entry will clobber Pt.
                continue

            generations = [group.generation.id for group in number.pokedex.version_groups]
            if generations:
                shown_generation = min(generations)
            else:
                shown_generation = None

            dex_numbers[dex_name] = [number.pokedex_number, shown_generation]

            if number.pokedex.id == 6: # Platinum Sinnoh dex
                # We want the Platinum version icon to stay a literal, or else we end up with "&lt;img ...", so we can't put it in the format string.
                dex_numbers[dex_name][0] = '{0} '.format(dex_numbers[dex_name][0]) + h.pokedex.version_icons(u'Platinum')
%>
    <dl>
        <dt>Introduced in</dt>
        <dd>${h.pokedex.generation_icon(c.pokemon.generation)}</dd>
        % for dex_name in sorted(dex_numbers.keys(), key=to_show.index):
        % if dex_name == 'New':
        <dt>Johto ${h.pokedex.generation_icon(2)}</dt>
        % elif dex_numbers[dex_name][1]:
        <dt>${dex_name} ${h.pokedex.generation_icon(dex_numbers[dex_name][1])}</dt>
        % else:
        <dt>${dex_name}</dt>
        % endif
        <dd>${dex_numbers[dex_name][0]}</dd>
        % endfor
    </dl>

    <h2>Names</h2>
    <dl>
        % for foreign_name in c.pokemon.normal_form.foreign_names:
        <dt>
            ${foreign_name.language.name}
            <img src="${h.static_uri('spline', "flags/{0}.png".format(foreign_name.language.iso3166))}" alt="">
        </dt>
        % if foreign_name.language.name == 'Japanese':
        <dd>${foreign_name.name} (${h.pokedex.romanize(foreign_name.name)})</dd>
        % else:
        <dd>${foreign_name.name}</dd>
        % endif
        % endfor
    </dl>
</div>
<div class="dex-column">
    <h2>Breeding</h2>
    <dl>
        <dt>Gender</dt>
        <dd>${h.pokedex.pokedex_img('gender-rates/%d.png' % c.pokemon.gender_rate, alt='')} ${h.pokedex.gender_rate_label[c.pokemon.gender_rate]}</dd>
        <dt>Egg groups</dt>
        <dd>
            <ul>
                % for i, egg_group in enumerate(c.pokemon.egg_groups):
                <li>${egg_group.name}</li>
                % endfor
            </ul>
        </dd>
        <dt>Steps to hatch</dt>
        <dd>${c.pokemon.evolution_chain.steps_to_hatch}</dd>
    </dl>

    <h2>Compatibility</h2>
    % if c.pokemon.egg_groups[0].id == 13:
    ## Egg group 13 is the special Ditto group
    <p>Ditto can breed with any other breedable Pokémon, but can never produce a Ditto egg.</p>
    % elif c.pokemon.egg_groups[0].id == 15:
    ## Egg group 15 is the special No Eggs group
    <p>${c.pokemon.name} cannot breed.</p>
    % else:
    <ul class="inline dex-pokemon-compatibility">
        % for pokemon in c.compatible_families:
        <li>${h.pokedex.pokemon_link(
            pokemon,
            h.pokedex.pokemon_sprite(pokemon, prefix='icons'),
            class_='dex-icon-link',
        )}</li>
        % endfor
    </ul>
    % endif
</div>
<div class="dex-column">
    <h2>Training</h2>
    <dl>
        <dt>Base EXP</dt>
        <dd>
            <span id="dex-pokemon-exp-base">${c.pokemon.base_experience}</span> <br/>
            <span id="dex-pokemon-exp">${h.pokedex.formulae.earned_exp(base_exp=c.pokemon.base_experience, level=100)}</span> EXP at level <input type="text" size="3" value="100" id="dex-pokemon-exp-level">
        </dd>
        <dt>Effort points</dt>
        <dd>
            <ul>
                % for pokemon_stat in c.pokemon.stats:
                % if pokemon_stat.effort:
                <li>${pokemon_stat.effort} ${pokemon_stat.stat.name}</li>
                % endif
                % endfor
            </ul>
        </dd>
        <dt>Capture rate</dt>
        <dd>${c.pokemon.capture_rate}</dd>
        <dt>Base happiness</dt>
        <dd>${c.pokemon.base_happiness}</dd>
        <dt>Growth rate</dt>
        <dd>${c.pokemon.evolution_chain.growth_rate.name}</dd>
        <dt>Wild held items</dt>
        <dd>
            % for generation, version_dict in sorted(c.held_items.items(), key=lambda x: x[0].id):
            <h3>${h.pokedex.generation_icon(generation)}</h3><table><tbody>
            ## "x and y" returns x if x is false; x might be None here and we'd
            ## rather not try to get None.id
            % for versions, item_records in sorted(version_dict.items(), \
                                                  key=lambda (k,v): k and k[0].id):
                % if not len(item_records):
                <tr>
                % if versions:
                <td>${h.pokedex.version_icons(*versions)}</td>
                % endif
                <td>None</td>
                </tr>
                % endif
                % for item, rarity in item_records:
                <tr>
                % if versions:
                <td>${h.pokedex.version_icons(*versions)}</td>
                % endif
                <td>
                    <span class="dex-pokemon-item-rarity">${rarity}%</span>
                    ${h.pokedex.item_link(item)}
                </td>
                </tr>
                % endfor
            % endfor
            </tbody></table>
            % endfor
        </dd>
    </dl>
</div>
</div>

<h1 id="evolution"><a href="#evolution" class="subtle">Evolution</a></h1>
<table class="dex-evolution-chain">
<thead>
<tr>
    <th>Baby</th>
    <th>Basic</th>
    <th>Stage 1</th>
    <th>Stage 2</th>
</tr>
</thead>
<tbody>
% for row in c.evolution_table:
<tr>
    % for col in row:
    ## Empty cell
    % if col == '':
    <td></td>
    % elif col != None:
    <td rowspan="${col['span']}"\
        % if col['pokemon'] == c.pokemon:
        ${h.literal(' class="selected"')}\
        % endif
    >
        % if col['pokemon'] == c.pokemon:
        <span class="dex-evolution-chain-pokemon">
            ${h.pokedex.pokemon_sprite(col['pokemon'], prefix='icons')}
            ${col['pokemon'].full_name}
        </span>
        % else:
        ${h.pokedex.pokemon_link(
            pokemon=col['pokemon'],
            content=h.pokedex.pokemon_sprite(col['pokemon'], prefix='icons')
                   + col['pokemon'].full_name,
            class_='dex-evolution-chain-pokemon',
        )}
        % endif
        % if col['pokemon'].evolution_method:
        <span class="dex-evolution-chain-method">
            % if col['pokemon'].evolution_parameter:
            ${col['pokemon'].evolution_method.name}:
            ${col['pokemon'].evolution_parameter}
            % else:
            ${col['pokemon'].evolution_method.name}
            % endif
        </span>
        % endif
    </td>
    % endif
    % endfor
</tr>
% endfor
</tbody>
</table>
% if c.pokemon.normal_form.form_group:
<h2 id="forms"> <a href="#forms" class="subtle">${c.pokemon.name} Forms</a> </h2>
<ul class="inline">
    % for form in [_.name for _ in c.pokemon.normal_form.form_sprites]:
<%
    link_class = 'dex-box-link'
    if form == c.pokemon.forme_name:
        link_class = link_class + ' selected'
%>\
    <li>${h.pokedex.pokemon_link(c.pokemon, h.pokedex.pokemon_sprite(c.pokemon, 'heartgold-soulsilver', form=form), form=form, class_=link_class)}</li>
    % endfor
</ul>
<p> ${c.pokemon.normal_form.form_group.description} </p>
% endif

<h1 id="stats"><a href="#stats" class="subtle">Stats</a></h1>
<%
    # Most people want to see the best they can get
    default_stat_level = 100
    default_stat_effort = 255
%>\
<table class="dex-pokemon-stats">
<col class="dex-col-stat-name">
<col class="dex-col-stat-bar">
<col class="dex-col-stat-pctile">
<col>
<col class="dex-col-stat-result">
<col class="dex-col-stat-result">
<tr>
    <th><!-- stat name --></th>
    <th><!-- bar and value --></th>
    <th><!-- percentile --></th>
    <td rowspan="11" class="vertical-line"></td>
    <th><label for="dex-pokemon-stats-level">Level</label></th>
    <th><input type="text" size="3" value="${default_stat_level}" disabled="disabled" id="dex-pokemon-stats-level"></th>
</tr>
<tr>
    <th><!-- stat name --></th>
    <th><!-- bar and value --></th>
    <th><!-- percentile --></th>
    <th><label for="dex-pokemon-stats-iv">Effort</label></th>
    <th><input type="text" size="3" value="${default_stat_effort}" disabled="disabled" id="dex-pokemon-stats-effort"></th>
</tr>
<tr class="header-row">
    <th><!-- stat name --></th>
    <th><!-- bar and value --></th>
    <th><abbr title="Percentile rank">Pctile</abbr></th>
    <th>Min IVs</th>
    <th>Max IVs</th>
</tr>
% for pokemon_stat in c.pokemon.stats:
<%
    stat_info = c.stats[pokemon_stat.stat.name]

    if pokemon_stat.stat.name == 'HP':
        stat_formula = h.pokedex.formulae.calculated_hp
    else:
        stat_formula = h.pokedex.formulae.calculated_stat
%>\
<tr class="color1">
    <th>${pokemon_stat.stat.name}</th>
    <td>
        <div class="dex-pokemon-stats-bar-container">
            <div class="dex-pokemon-stats-bar" style="margin-right: ${(1 - stat_info['percentile']) * 100}%; background-color: ${stat_info['background']}; border-color: ${stat_info['border']};">${pokemon_stat.base_stat}</div>
        </div>
    </td>
    <td class="dex-pokemon-stats-pctile">${"%0.1f" % (stat_info['percentile'] * 100)}</td>
    <td class="dex-pokemon-stats-result">${stat_formula(pokemon_stat.base_stat, level=default_stat_level, iv=0, effort=default_stat_effort)}</td>
    <td class="dex-pokemon-stats-result">${stat_formula(pokemon_stat.base_stat, level=default_stat_level, iv=31, effort=default_stat_effort)}</td>
</tr>
% endfor
<tr class="horizontal-line"><td colspan="6"></td></tr>
<tr class="color1">
    <th>Total</th>
    <td>
        <div class="dex-pokemon-stats-bar-container">
            <div class="dex-pokemon-stats-bar" style="margin-right: ${(1 - c.stats['total']['percentile']) * 100}%; background-color: ${c.stats['total']['background']}; border-color: ${c.stats['total']['border']};">${c.stats['total']['value']}</div>
        </div>
    </td>
    <td class="dex-pokemon-stats-pctile">${"%0.1f" % (c.stats['total']['percentile'] * 100)}</td>
    <td></td>
    <td></td>
</tr>
</table>

<h1 id="flavor"><a href="#flavor" class="subtle">Flavor</a></h1>

<ul class="see-also">
<li> <img src="${h.static_uri('spline', 'icons/arrow-000-medium.png')}" alt="See also:"> <a href="${url.current(action='pokemon_flavor')}">All versions' flavor text and sprites</a> </li>
</ul>

<div class="dex-column-container">
<div class="dex-column-2x">
    <h2>Flavor Text</h2>
    <dl class="dex-pokemon-flavor-text">
<%
        class_ = ''
        if session.get('cheat_obdurate', False):
            class_ = ' class="dex-obdurate"'
%>\
        % for version_name in u'Diamond', u'Pearl', u'Platinum':
        <dt>${h.pokedex.version_icons(version_name)}</dt>
        <dd${h.literal(class_)}>${c.flavor_text[version_name]}</dd>
        % endfor
    </dl>
</div>
<div class="dex-column">
    ## Only showing current generation's sprites and text
    <h2>Sprites</h2>
    ${h.pokedex.pokemon_sprite(c.pokemon, prefix='heartgold-soulsilver')}
    ${h.pokedex.pokemon_sprite(c.pokemon, prefix='heartgold-soulsilver/frame2')}
    ${h.pokedex.pokemon_sprite(c.pokemon, prefix='heartgold-soulsilver/shiny')}
    ${h.pokedex.pokemon_sprite(c.pokemon, prefix='heartgold-soulsilver/shiny/frame2')}
    <br/>
    % if c.pokemon.has_gen4_fem_sprite:
    ${h.pokedex.pokemon_sprite(c.pokemon, prefix='heartgold-soulsilver/female')}
    ${h.pokedex.pokemon_sprite(c.pokemon, prefix='heartgold-soulsilver/female/frame2')}
    ${h.pokedex.pokemon_sprite(c.pokemon, prefix='heartgold-soulsilver/shiny/female')}
    ${h.pokedex.pokemon_sprite(c.pokemon, prefix='heartgold-soulsilver/shiny/female/frame2')}
    % endif
</div>
</div>

<div class="dex-column-container">
<div class="dex-column">
    <h2>Miscellany</h2>
    <dl>
        <dt>Species</dt>
        <dd>${c.pokemon.species}</dd>
        <dt>Color</dt>
        <dd>${c.pokemon.color}</dd>
        <dt>Cry</dt>
        <dd>${h.HTML.a('download mp3', href=url(controller='dex', action='media', path='cries/%d.mp3' % c.pokemon.national_id))}</dd>
        % if c.pokemon.generation.id <= 3:
        <dt>Habitat ${h.pokedex.generation_icon(3)}</dt>
        <dd>${h.pokedex.pokedex_img('chrome/habitats/%s.png' % h.pokedex.filename_from_name(c.pokemon.habitat))} ${c.pokemon.habitat}</dd>
        % endif
        <dt>Pawprint</dt>
        <dd>${h.pokedex.pokemon_sprite(c.pokemon.normal_form, prefix='pawprints')}</dd>
        <dt>Shape</dt>
        <dd>
            ${h.pokedex.pokedex_img('chrome/shapes/%d.png' % c.pokemon.shape.id, alt='')}
            ${c.pokemon.shape.awesome_name}
        </dd>
    </dl>
</div>
<div class="dex-column">
    <h2>Height</h2>
    <div class="dex-size">
        <div class="dex-size-trainer">
            ${h.pokedex.pokedex_img('chrome/trainer-male.png', alt='Trainer dude', style="height: %.2f%%" % (c.heights['trainer'] * 100))}
            <p class="dex-size-value">
                <input type="text" size="6" value="${h.pokedex.format_height_imperial(c.trainer_height)}" disabled="disabled" id="dex-pokemon-height">
            </p>
        </div>
        <div class="dex-size-pokemon">
            ${h.pokedex.pokemon_sprite(c.pokemon, prefix='cropped-pokemon', style="height: %.2f%%;" % (c.heights['pokemon'] * 100))}
            <div class="js-dex-size-raw">${c.pokemon.height}</div>
            <p class="dex-size-value">
                ${h.pokedex.format_height_imperial(c.pokemon.height)} <br/>
                ${h.pokedex.format_height_metric(c.pokemon.height)}
            </p>
        </div>
    </div>
</div>
<div class="dex-column">
    <h2>Weight</h2>
    <div class="dex-size">
        <div class="dex-size-trainer">
            ${h.pokedex.pokedex_img('chrome/trainer-female.png', alt='Trainer dudette', style="height: %.2f%%" % (c.weights['trainer'] * 100))}
            <p class="dex-size-value">
                <input type="text" size="6" value="${h.pokedex.format_weight_imperial(c.trainer_weight)}" disabled="disabled" id="dex-pokemon-weight">
            </p>
        </div>
        <div class="dex-size-pokemon">
            ${h.pokedex.pokemon_sprite(c.pokemon, prefix='cropped-pokemon', style="height: %.2f%%;" % (c.weights['pokemon'] * 100))}
            <div class="js-dex-size-raw">${c.pokemon.weight}</div>
            <p class="dex-size-value">
                ${h.pokedex.format_weight_imperial(c.pokemon.weight)} <br/>
                ${h.pokedex.format_weight_metric(c.pokemon.weight)}
            </p>
        </div>
    </div>
</div>
</div>

<h1 id="locations"><a href="#locations" class="subtle">Locations</a></h1>
<ul class="see-also">
<li> <img src="${h.static_uri('spline', 'icons/overlay/map--arrow.png')}" alt="See also:"> <a href="${url.current(action='pokemon_locations')}">Ridiculously detailed breakdown</a> </li>
</ul>

<dl class="dex-simple-encounters">
    ## Sort versions by order, which happens to be id
    % for version, terrain_etc in sorted(c.locations.items(), \
                                         key=lambda (k, v): k.id):
    <dt>${version.name} ${h.pokedex.version_icons(version)}</dt>
    <dd>
        ## Sort terrain by name
        % for terrain, area_condition_encounters in sorted(terrain_etc.items(), \
                                                           key=lambda (k, v): k.id):
        <div class="dex-simple-encounters-terrain">
            ${h.pokedex.pokedex_img('encounters/' + c.encounter_terrain_icons.get(terrain.name, 'unknown.png'), \
                                    alt=terrain.name)}
            <ul>
                ## Sort locations by name
                % for location_area, (conditions, combined_encounter) \
                    in sorted(area_condition_encounters.items(), \
                              key=lambda (k, v): (k.location.name, k.name)):
                <li title="${combined_encounter.level} ${combined_encounter.rarity}% ${';'.join(_.name for _ in conditions)}">
                    <a href="${url(controller="dex", action="locations", name=location_area.location.name.lower())}${'#area:' + location_area.name if location_area.name else ''}">
                        ${location_area.location.name}${', ' + location_area.name if location_area.name else ''}
                    </a>
                </li>
                % endfor
            </ul>
        </div>
        % endfor
    </dd>
    % endfor
</dl>

<h1 id="moves"><a href="#moves" class="subtle">Moves</a></h1>
<table class="dex-pokemon-moves dex-pokemon-pokemon-moves striped-rows">
## COLUMNS
% for i, column in enumerate(c.move_columns):
% if i in c.move_divider_columns:
<col class="dex-col-version dex-col-last-version">
% else:
<col class="dex-col-version">
% endif
% endfor
## HEADERS
% for method, method_list in c.moves:
<%
    method_id = "moves:" + re.sub('\W+', '-', method.name.lower())
%>\
<tr class="header-row" id="${method_id}">
    % for column in c.move_columns:
    ${lib.pokemon_move_table_column_header(column)}
    % endfor
    <th>Move</th>
    <th>Type</th>
    <th>Class</th>
    <th>PP</th>
    <th>Power</th>
    <th>Acc</th>
    <th>Pri</th>
    <th>Effect</th>
</tr>
<tr class="subheader-row">
    <th colspan="${len(c.move_columns) + 8}"><a href="#${method_id}" class="subtle"><strong>${method.name}</strong></a>: ${method.description}</th>
</tr>
## DATA
% for move, version_group_data in method_list:
% if move.type in c.pokemon.types:
<tr class="better-move">
% else:
<tr>
% endif
    % for column in c.move_columns:
    ${lib.pokemon_move_table_method_cell(column, method, version_group_data)}
    % endfor

    <td><a href="${url(controller='dex', action='moves', name=move.name.lower())}">${move.name}</a></td>
    % if move.type in c.pokemon.types:
    <td class="better-move-reason">
    % else:
    <td>
    % endif
        ${h.pokedex.type_link(move.type)}
    </td>
    % if move.damage_class.name == c.better_damage_class:
    <td class="better-move-reason">
    % else:
    <td>
    % endif
        ${h.pokedex.damage_class_icon(move.damage_class)}
    </td>
    <td>${move.pp}</td>
    <td>${move.power}</td>
    <td>${move.accuracy}%</td>
    ## Priority is colored red for slow and green for fast
    % if move.priority == 0:
    <td></td>
    % elif move.priority > 0:
    <td class="dex-priority-fast">${move.priority}</td>
    % else:
    <td class="dex-priority-slow">${move.priority}</td>
    % endif
    <td class="effect">${h.literal(move.short_effect.as_html)}</td>
</tr>
% endfor
% endfor
</table>

<h1 id="links"><a href="#links" class="subtle">External Links</a></h1>
<%
    # Some sites don't believe in Unicode URLs.  Scoff, scoff.
    # And they all do it differently.  Ugh, ugh.
    if c.pokemon.name == u'Nidoran♀':
        lp_name = 'Nidoran(f)'
        ghpd_name = 'nidoran_f'
        smogon_name = 'nidoran-f'
    elif c.pokemon.name == u'Nidoran♂':
        lp_name = 'Nidoran(m)'
        ghpd_name = 'nidoran_m'
        smogon_name = 'nidoran-m'
    else:
        lp_name = c.pokemon.name
        ghpd_name = re.sub(' ', '_', c.pokemon.name.lower())
        ghpd_name = re.sub('[^\w-]', '', ghpd_name)
        smogon_name = ghpd_name

    if c.pokemon.forme_base_pokemon:
        if c.pokemon.forme_name == 'sandy':
            smogon_name += '-g'
        elif c.pokemon.forme_name == 'mow':
            smogon_name += '-c'
        elif c.pokemon.forme_name in ('fan', 'trash'):
            smogon_name += '-s'
        else:
            smogon_name += '-' + c.pokemon.forme_name[0].lower()
%>
<ul class="classic-list">
% if c.pokemon.generation.id <= 1:
<li>${h.pokedex.generation_icon(1)} <a href="http://www.math.miami.edu/~jam/azure/pokedex/species/${"%03d" % c.pokemon.national_id}.htm">Azure Heights</a></li>
% endif
<li><a href="http://bulbapedia.bulbagarden.net/wiki/${re.sub(' ', '_', c.pokemon.name)}_%28Pok%C3%A9mon%29">Bulbapedia</a></li>
% if c.pokemon.generation.id <= 2:
<li>${h.pokedex.generation_icon(2)} <a href="http://www.pokemondungeon.com/pokedex/${ghpd_name}.shtml">Gengar and Haunter's Pokémon Dungeon</a></li>
% endif
<li><a href="http://www.legendarypokemon.net/pokedex/${lp_name}">Legendary Pokémon</a></li>
<li><a href="http://www.psypokes.com/dex/psydex/${"%03d" % c.pokemon.national_id}">PsyPoke</a></li>
<li><a href="http://www.serebii.net/pokedex-dp/${"%03d" % c.pokemon.national_id}.shtml">Serebii</a></li>
<li><a href="http://www.smogon.com/dp/pokemon/${smogon_name}">Smogon</a></li>
</ul>
