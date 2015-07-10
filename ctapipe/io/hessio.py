"""
Components to read HESSIO data.  

This requires the hessio python library to be installed
"""

from ctapipe.core import  Container
from collections import defaultdict

import logging
logger = logging.getLogger(__name__)

try:
    import hessio
except ImportError as err:
    logger.fatal("the `hessio` python module is required to access MC data: {}"
                 .format(err))
    raise err


def hessio_event_source(url, max_events=None):
    """A generator that streams data from an EventIO/HESSIO MC data file
    (e.g. a standard CTA data file.)

    Parameters
    ----------
    url: string
        path to file to open
    max_events: int, optional
        maximum number of events to read
    """

    ret = hessio.file_open(url)

    if ret is not 0:
        raise RuntimeError("hessio_event_source failed to open '{}'"
                           .format(url))

    counter = 0
    eventstream = hessio.move_to_next_event()
    cont = Container("hessio_data")
    cont.add_item("run_id")
    cont.add_item("event_id")
    cont.add_item("tels_with_data")
    cont.add_item("sampledata")
    cont.add_item("sumdata")
    cont.add_item("num_channels")
    cont.meta.add_item('hessio_source.input',url)
    cont.meta.add_item('hessio_source.max_events',max_events)
    cont.add_item('pixel_pos')

    cont.num_channels = defaultdict(int)
    cont.pixel_pos = defaultdict(int)
    
    for run_id, event_id in eventstream:

        cont.run_id = run_id
        cont.event_id = event_id
        cont.tels_with_data = hessio.get_teldata_list()

        # this should be done in a nicer way to not re-allocate
        # the data each time

        cont.sampledata = defaultdict(dict)
        cont.sumdata = defaultdict(dict)
        
        for tel_id in cont.tels_with_data:
            if tel_id not in cont.pixel_pos:
                cont.pixel_pos[tel_id] = hessio.get_pixel_position(tel_id)
                cont.num_channels[tel_id] = hessio.get_num_channel(tel_id)
                
            for chan in range(cont.num_channels[tel_id]):
                cont.sampledata[tel_id][chan] \
                    = hessio.get_adc_sample(channel=chan,
                                            telescopeId=tel_id)
                cont.sumdata[tel_id][chan] \
                    = hessio.get_adc_sum(channel=chan,
                                         telescopeId=tel_id)
        yield cont
        counter += 1

        if counter > max_events:
            return
    