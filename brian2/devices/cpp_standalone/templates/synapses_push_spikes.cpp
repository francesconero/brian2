////////////////////////////////////////////////////////////////////////////
//// MAIN CODE /////////////////////////////////////////////////////////////

{% macro cpp_file() %}

{# USES_VARIABLES { _spikespace } #}

#include "code_objects/{{codeobj_name}}.h"
#include<math.h>
#include<stdint.h>
#include "brianlib/common_math.h"

void _run_{{codeobj_name}}()
{
	using namespace brian;
    ///// CONSTANTS ///////////
	%CONSTANTS%
	///// POINTERS ////////////
    {{pointers_lines|autoindent}}

    //// MAIN CODE ////////////
	// we do advance at the beginning rather than at the end because it saves us making
	// a copy of the current spiking synapses
	{{owner.name}}.queue->advance();
	{{owner.name}}.queue->push({{_spikespace}}, {{_spikespace}}[_num_spikespace-1]);
	{{owner.name}}.queue->peek();
}
{% endmacro %}

////////////////////////////////////////////////////////////////////////////
//// HEADER FILE ///////////////////////////////////////////////////////////

{% macro h_file() %}
#ifndef _INCLUDED_{{codeobj_name}}
#define _INCLUDED_{{codeobj_name}}

#include "objects.h"

void _run_{{codeobj_name}}();

#endif
{% endmacro %}
