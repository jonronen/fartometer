/**
 * Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
 * SPDX-License-Identifier: Apache-2.0.
 */
#include <aws/crt/Api.h>
#include <aws/crt/StlAllocator.h>

#include <aws/iot/MqttClient.h>

#include <algorithm>
#include <aws/crt/UUID.h>
#include <condition_variable>
#include <iostream>
#include <mutex>

#include <stdio.h>
#include <fcntl.h>
#include <stdlib.h>
#include <unistd.h>
#include <string.h>
#include <errno.h>
#include <time.h>

#include "ccs811_sense.h"

using namespace Aws::Crt;

static void s_printHelp()
{
    fprintf(stdout, "Usage:\n");
    fprintf(
        stdout,
        "fartometer --endpoint <endpoint> --cert <path to cert>"
        " --key <path to key> --ca_file <optional: path to custom ca>\n\n");
    fprintf(stdout, "endpoint: the endpoint of the mqtt server not including a port\n");
    fprintf(
        stdout,
        "cert: path to your client certificate in PEM format\n");
    fprintf(stdout, "key: path to your key in PEM format\n");
    fprintf(stdout, "client_id: client id to use (optional)\n");
    fprintf(
        stdout,
        "ca_file: Optional, if the mqtt server uses a certificate that's not already"
        " in your trust store, set this.\n");
    fprintf(stdout, "\tIt's the path to a CA file in PEM format\n");
}

static bool s_cmdOptionExists(char **begin, char **end, const String &option)
{
    return std::find(begin, end, option) != end;
}

static char *s_getCmdOption(char **begin, char **end, const String &option)
{
    char **itr = std::find(begin, end, option);
    if (itr != end && ++itr != end)
    {
        return *itr;
    }
    return 0;
}

static const char *get_location()
{
    static const unsigned int LOCATION_MAX_SIZE = 64;
    static char location[LOCATION_MAX_SIZE+1];
    static const char default_location[] = "Home";
    int f = open("location.txt", O_RDONLY);

    if (f < 0) {
        printf("Error opening file: %d\n", errno);
        return default_location;
    }

    int ret = read(f, location, LOCATION_MAX_SIZE);
    if (ret <= 0 || (unsigned int)ret >= LOCATION_MAX_SIZE || ret <= 0) {
        printf("Invalid location from file\n");
        return default_location;
    }
    location[ret] = '\n';

    while (ret > 0 && isspace(location[ret])) {
        location[ret] = 0;
        ret--;
    }

    printf("Using location %s\n", location);

    return location;
}


int main(int argc, char *argv[])
{

    /************************ Setup the Lib ****************************/
    /*
     * Do the global initialization for the API.
     */
    ApiHandle apiHandle;

    String endpoint;
    String certificatePath;
    String keyPath;
    String caFile;
    String topic = "sensor_report";
    String clientId(Aws::Crt::UUID().ToString());
    const char *location = get_location();

    /*********************** Parse Arguments ***************************/
    if (!s_cmdOptionExists(argv, argv + argc, "--endpoint") ||
        !s_cmdOptionExists(argv, argv + argc, "--key") ||
        !s_cmdOptionExists(argv, argv + argc, "--cert") ||
        !s_cmdOptionExists(argv, argv + argc, "--ca_file") ||
        !s_cmdOptionExists(argv, argv + argc, "--client_id"))
    {
        s_printHelp();
        return 0;
    }

    endpoint = s_getCmdOption(argv, argv + argc, "--endpoint");
    keyPath = s_getCmdOption(argv, argv + argc, "--key");
    certificatePath = s_getCmdOption(argv, argv + argc, "--cert");
    caFile = s_getCmdOption(argv, argv + argc, "--ca_file");
    clientId = s_getCmdOption(argv, argv + argc, "--client_id");

    /********************** Now Setup an Mqtt Client ******************/
    /*
     * You need an event loop group to process IO events.
     * If you only have a few connections, 1 thread is ideal
     */
    Io::EventLoopGroup eventLoopGroup(1);
    if (!eventLoopGroup)
    {
        fprintf(
            stderr, "Event Loop Group Creation failed with error %s\n", ErrorDebugString(eventLoopGroup.LastError()));
        exit(-1);
    }

    Aws::Crt::Io::DefaultHostResolver defaultHostResolver(eventLoopGroup, 1, 5);
    Io::ClientBootstrap bootstrap(eventLoopGroup, defaultHostResolver);

    if (!bootstrap)
    {
        fprintf(stderr, "ClientBootstrap failed with error %s\n", ErrorDebugString(bootstrap.LastError()));
        exit(-1);
    }

    Aws::Iot::MqttClientConnectionConfigBuilder builder;

    builder = Aws::Iot::MqttClientConnectionConfigBuilder(certificatePath.c_str(), keyPath.c_str());
    builder.WithCertificateAuthority(caFile.c_str());
    builder.WithEndpoint(endpoint);

    auto clientConfig = builder.Build();

    if (!clientConfig)
    {
        fprintf(
            stderr,
            "Client Configuration initialization failed with error %s\n",
            ErrorDebugString(clientConfig.LastError()));
        exit(-1);
    }

    Aws::Iot::MqttClient mqttClient(bootstrap);
    /*
     * Since no exceptions are used, always check the bool operator
     * when an error could have occurred.
     */
    if (!mqttClient)
    {
        fprintf(stderr, "MQTT Client Creation failed with error %s\n", ErrorDebugString(mqttClient.LastError()));
        exit(-1);
    }

    /*
     * Now create a connection object. Note: This type is move only
     * and its underlying memory is managed by the client.
     */
    auto connection = mqttClient.NewConnection(clientConfig);

    if (!connection)
    {
        fprintf(stderr, "MQTT Connection Creation failed with error %s\n", ErrorDebugString(mqttClient.LastError()));
        exit(-1);
    }

    /*
     * In a real world application you probably don't want to enforce synchronous behavior
     * but this is a sample console application, so we'll just do that with a condition variable.
     */
    std::promise<bool> connectionCompletedPromise;
    std::promise<void> connectionClosedPromise;

    /*
     * This will execute when an mqtt connect has completed or failed.
     */
    auto onConnectionCompleted = [&](Mqtt::MqttConnection &, int errorCode, Mqtt::ReturnCode returnCode, bool) {
        if (errorCode)
        {
            fprintf(stdout, "Connection failed with error %s\n", ErrorDebugString(errorCode));
            connectionCompletedPromise.set_value(false);
        }
        else
        {
            if (returnCode != AWS_MQTT_CONNECT_ACCEPTED)
            {
                fprintf(stdout, "Connection failed with mqtt return code %d\n", (int)returnCode);
                connectionCompletedPromise.set_value(false);
            }
            else
            {
                fprintf(stdout, "Connection completed successfully\n");
                connectionCompletedPromise.set_value(true);
            }
        }
    };

    auto onInterrupted = [&](Mqtt::MqttConnection &, int error) {
        fprintf(stdout, "Connection interrupted with error %s\n", ErrorDebugString(error));
    };

    auto onResumed = [&](Mqtt::MqttConnection &, Mqtt::ReturnCode, bool) { fprintf(stdout, "Connection resumed\n"); };

    /*
     * Invoked when a disconnect message has completed.
     */
    auto onDisconnect = [&](Mqtt::MqttConnection &) {
        {
            fprintf(stdout, "Disconnect completed\n");
            connectionClosedPromise.set_value();
        }
    };

    connection->OnConnectionCompleted = std::move(onConnectionCompleted);
    connection->OnDisconnect = std::move(onDisconnect);
    connection->OnConnectionInterrupted = std::move(onInterrupted);
    connection->OnConnectionResumed = std::move(onResumed);

    /*
     * Actually perform the connect dance.
     * This will use default ping behavior of 1 hour and 3 second timeouts.
     * If you want different behavior, those arguments go into slots 3 & 4.
     */
    fprintf(stdout, "Connecting...\n");
    if (!connection->Connect(clientId.c_str(), false, 1000))
    {
        fprintf(stderr, "MQTT Connection failed with error %s\n", ErrorDebugString(connection->LastError()));
        exit(-1);
    }

    /* initialize the sensor */
    ccs811_init();

    unsigned int sample_counter = 0;

    if (connectionCompletedPromise.get_future().get())
    {
        while (true)
        {
            sleep(1);

            env_values_t env_values;
            if (get_env_sample(env_values) < 0)
                continue;

            if (!env_values.valid)
                continue;

            sample_counter++;

            /* allow at least 20 minutes of consistent operation, send report every 10 minutes */
            if (sample_counter < 20 * 60)
                continue;

            if (sample_counter % (10 * 60))
                continue;

            char input[128];
            snprintf(input,
                     sizeof(input),
                     "{\"location\": \"%s\", \"eco2\": %u, \"etvoc\": %u}",
                     location,
                     env_values.co2,
                     env_values.tvoc);
            input[sizeof(input)-1] = '\0';

            printf("Sending %s on topic %s\n", input, topic.c_str());

            ByteBuf payload = ByteBufNewCopy(DefaultAllocator(), (const uint8_t *)input, strlen(input));
            ByteBuf *payloadPtr = &payload;

            auto onPublishComplete = [payloadPtr](Mqtt::MqttConnection &, uint16_t packetId, int errorCode) {
                aws_byte_buf_clean_up(payloadPtr);

                if (packetId)
                {
                    fprintf(stdout, "Operation on packetId %d Succeeded\n", packetId);
                }
                else
                {
                    fprintf(stdout, "Operation failed with error %s\n", aws_error_debug_str(errorCode));
                }
            };
            connection->Publish(topic.c_str(), AWS_MQTT_QOS_AT_LEAST_ONCE, false, payload, onPublishComplete);
        }
    }

    /* Disconnect */
    if (connection->Disconnect())
    {
        connectionClosedPromise.get_future().wait();
    }
    return 0;
}
